"""AnalogArrayBase — shared base for sensors that read a flat vector of analog
channels from a microcontroller over the forge link protocol.

An array sensor (mq_array gas, future pressure_array) is decoupled from the MCU
that feeds it: the firmware streams raw int16 channels; this base decodes them
(core.mcu_link), maps each frame index to a signal name via the sensor's
configured `channels`, and broadcasts a reading. Raw counts are ALWAYS present —
subclasses add calibrated/derived values by overriding `enrich()`, never by
replacing the raw lane. That is the firmware↔Python boundary: bytes in, meaning
added here.

The serial read loop mirrors sensors/tf_mini (open, resync, retry on error).
pyserial is imported lazily so core/ stays importable on machines without it.
"""
from __future__ import annotations

import logging
import threading
import time

from core.mcu_link import FrameStream
from core.models import SensorReading
from core.sensor_base import SensorBase

log = logging.getLogger(__name__)


class AnalogArrayBase(SensorBase):
    """Base for MCU-fed analog array sensors. Subclasses set `sensor_type` and
    may override `enrich()` to add calibrated values."""

    sensor_type: str = "analog_array"
    BAUD_DEFAULT = 115_200
    DEFAULT_PORT = "/dev/ttyUSB0"

    def __init__(self, sensor_id, config) -> None:
        super().__init__(sensor_id, config)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._healthy = False

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
            self._thread.join(timeout=3)

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy

    # ── Overridable interpretation hook ───────────────────────────────────────

    def enrich(self, data: dict, raw: dict[str, int]) -> None:
        """Add calibrated/derived values to `data`. Default: nothing (raw only).

        `raw` is {signal: count}; subclasses read it and write extra keys into
        `data` (which already carries data["raw"] = raw). The raw lane is never
        removed, so the underlying signal is always recoverable.
        """

    # ── Reading construction ──────────────────────────────────────────────────

    def _reading(self, frame) -> SensorReading:
        raw: dict[str, int] = {}
        for ch in self.config.channels:
            if 0 <= ch.index < len(frame.samples):
                raw[ch.signal] = int(frame.samples[ch.index])
        data: dict = {"seq": frame.seq, "raw": raw}
        self.enrich(data, raw)
        return SensorReading(
            sensor_id=self.id,
            sensor_type=self.sensor_type,
            timestamp=time.time(),
            data=data,
        )

    # ── Background serial loop ────────────────────────────────────────────────

    def _read_loop(self) -> None:
        import serial  # lazy: hardware dep, keeps core/ importable without it

        port = self.config.connection.port or self.DEFAULT_PORT
        baud = self.config.connection.baud_rate or self.BAUD_DEFAULT
        stream = FrameStream()

        while not self._stop_event.is_set():
            try:
                with serial.Serial(port, baud, timeout=1) as ser:
                    log.info("%s: opened %s at %d baud", self.id, port, baud)
                    self._healthy = True
                    while not self._stop_event.is_set():
                        chunk = ser.read(64)
                        if not chunk:
                            continue
                        for frame in stream.feed(chunk):
                            self._broadcast(self._reading(frame))
            except serial.SerialException as exc:
                self._healthy = False
                log.warning("%s: serial error — %s — retrying in 2s", self.id, exc)
                self._stop_event.wait(2)

        self._healthy = False
