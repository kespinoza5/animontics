from __future__ import annotations

import logging
import struct
import threading
import time

from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
from sensors.audio_in.driver import AlsaCapture, block_stats

log = logging.getLogger(__name__)

#: Binary frame header: frame_id, channels, bits-per-sample, sample_rate.
#: Payload is the raw interleaved S16_LE block.
_FRAME_HEADER = struct.Struct("<IHHI")


@register("audio_in")
class AudioIn(SensorBase):
    """Stereo audio capture (PCM1808 over the shared-clock I2S bus) — audition.

    Two lanes, per the high-rate array convention:
      - **binary frame lane** (`/sensors/<id>/frames`): every captured block,
        header `<IHHI>` = (frame_id, channels, bits, rate) + raw interleaved
        S16_LE samples — the waveform/feature stream for viewers and the
        inference hub. ~2.3 Mbps at 48 kHz stereo: trivial for the network lane.
      - **JSON lane**: rate-limited per-channel level summaries (rms / peak /
        dBFS), throttled to ~`params.json_hz` (default 5) readings/s.

    Connectionless (the I2S bus is OS plumbing, not a fleet-config wiring
    detail); `params`: alsa_device ("hw:0,0"), sample_rate (48000),
    channels (2), block_ms (50), json_hz (5).

    Capture uses pyalsaaudio when present, else an `arecord` raw pipe — and on
    a machine with neither (Windows dev) the sensor stays cleanly unhealthy.
    """

    sensor_type = "audio_in"
    produces_frames = True

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        p = config.params or {}
        self._device = str(p.get("alsa_device", "hw:0,0"))
        self._rate = int(p.get("sample_rate", 48000))
        self._channels = int(p.get("channels", 2))
        self._block_frames = max(1, self._rate * int(p.get("block_ms", 50)) // 1000)
        self._json_period = 1.0 / float(p.get("json_hz", 5))
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._healthy = False
        self._frame_id = 0

    # ── SensorBase contract ───────────────────────────────────────────────────

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop, daemon=True, name=f"sensor-{self.id}"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy

    # ── Capture loop ──────────────────────────────────────────────────────────

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            cap = AlsaCapture(self._device, self._rate, self._channels,
                              self._block_frames)
            try:
                cap.open()
                log.info("%s: capture open on %s (%d Hz, %d ch)",
                         self.id, self._device, self._rate, self._channels)
                self._healthy = True
                self._inner_loop(cap)
            except Exception as exc:
                self._healthy = False
                log.warning("%s: capture error — %s — retrying in 3s", self.id, exc)
                self._stop_event.wait(3)
            finally:
                cap.close()
        self._healthy = False

    def _inner_loop(self, cap: AlsaCapture) -> None:
        next_json = 0.0
        while not self._stop_event.is_set():
            block = cap.read()
            if not block:
                raise RuntimeError("capture stream ended")

            self._frame_id = (self._frame_id + 1) & 0xFFFFFFFF
            self._broadcast_frame(
                _FRAME_HEADER.pack(self._frame_id, self._channels, 16, self._rate)
                + block
            )

            now = time.time()
            if now >= next_json:
                next_json = now + self._json_period
                stats = block_stats(block, self._channels)
                self._broadcast(SensorReading(
                    sensor_id=self.id,
                    sensor_type=self.sensor_type,
                    timestamp=now,
                    data={
                        "frame_id": self._frame_id,
                        "rate": self._rate,
                        "channels": {f"ch{i}": s for i, s in enumerate(stats)},
                    },
                ))
