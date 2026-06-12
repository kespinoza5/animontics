from __future__ import annotations

import logging
import subprocess

from core.effector_base import EffectorBase, register_effector
from core.gpio import NullOutputLine, OutputLine, make_output_line

log = logging.getLogger(__name__)


@register_effector("speaker")
class Speaker(EffectorBase):
    """Audio playback through ALSA (MAX98357A on the shared-clock I2S DOUT).

    Two lanes:
      - **stream** — `WS /effectors/<id>/stream`: raw interleaved S16_LE audio
        fed straight to an `aplay` raw pipe (spawned lazily on first chunk,
        respawned on a broken pipe). The same format `sensors/audio_in`
        captures, so loopback tests are byte-symmetric.
      - **request** — `{"on": true|false}`: the amp's SD pin via a
        `core/gpio.py` output line (`params.sd_line`). Gating the amp is a
        GPIO, not a relay — it costs nothing and kills idle hiss.

    Config keys (params): alsa_device ("hw:0,0"), sample_rate (48000),
    channels (2), sd_line ({backend: libgpiod, …} | absent = always enabled).

    Volume/limiting note: the 1 W ADA1313 driver hangs off a ~1.8 W-capable
    amp — the gain strap is the hardware ceiling; software keeps meaning
    (what to say) and the amp keeps physics (how loud it can be).
    """

    effector_type = "speaker"
    lanes = ("request", "stream")

    def __init__(self, effector_id, config) -> None:
        super().__init__(effector_id, config)
        p = config.params or {}
        self._device = str(p.get("alsa_device", "hw:0,0"))
        self._rate = int(p.get("sample_rate", 48000))
        self._channels = int(p.get("channels", 2))
        self._sd: OutputLine = NullOutputLine("not attached")
        self._proc: subprocess.Popen | None = None
        self._bytes = 0
        self._on = True

    # ── Binding ───────────────────────────────────────────────────────────────

    def attach_devices(self, devices) -> None:
        super().attach_devices(devices)
        self._sd = make_output_line(self.config.params.get("sd_line"),
                                    devices=devices)

    # ── Request lane: SD gate ─────────────────────────────────────────────────

    def handle_request(self, payload: dict) -> dict:
        if "on" not in payload:
            return {"error": "expected {'on': bool}"}
        self._on = bool(payload["on"])
        self._sd.set(self._on)
        self._state["on"] = self._on
        return {"set": {"on": self._on}}

    # ── Stream lane: raw S16_LE → aplay ───────────────────────────────────────

    def _player(self) -> subprocess.Popen | None:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        try:
            self._proc = subprocess.Popen(
                ["aplay", "-D", self._device, "-f", "S16_LE",
                 "-r", str(self._rate), "-c", str(self._channels),
                 "-t", "raw", "-q"],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        except OSError as exc:                       # no aplay (dev machine)
            log.warning("speaker %s: aplay unavailable — %s", self.id, exc)
            self._proc = None
        return self._proc

    def feed(self, chunk: bytes) -> None:
        self._bytes += len(chunk)
        proc = self._player()
        if proc is None or proc.stdin is None:
            return                                   # counted, not played
        try:
            proc.stdin.write(chunk)
        except (BrokenPipeError, OSError):
            log.warning("speaker %s: playback pipe broke — respawning", self.id)
            self._proc = None

    def state(self) -> dict:
        return {"on": self._on, "bytes_fed": self._bytes,
                "playing": self._proc is not None and self._proc.poll() is None}

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["value"] = "S16_LE stream + {'on': bool} gate"
        d["format"] = {"rate": self._rate, "channels": self._channels, "bits": 16}
        return d

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._sd.set(self._on)                       # amp enabled by default

    def stop(self) -> None:
        if self._proc is not None:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
            self._proc = None
        self._sd.close()
