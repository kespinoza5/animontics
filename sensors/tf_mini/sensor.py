from __future__ import annotations

import logging
import threading
import time

import serial

from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
from sensors.tf_mini.driver import parse_frame

log = logging.getLogger(__name__)


@register("tf_mini")
class TFminiSensor(SensorBase):
    """
    Benewake TF Mini Plus LiDAR over UART.

    Config connection fields:
      type:      uart
      port:      /dev/ttyAMA0  (or /dev/ttyUSB0, etc.)
      baud_rate: 115200
    """

    BAUD_DEFAULT = 115_200

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._healthy = False

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

    # ── Background reading loop ───────────────────────────────────────────────

    def _read_loop(self) -> None:
        port      = self.config.connection.port or "/dev/ttyAMA0"
        baud_rate = self.config.connection.baud_rate or self.BAUD_DEFAULT

        while not self._stop_event.is_set():
            try:
                with serial.Serial(port, baud_rate, timeout=1) as ser:
                    log.info("%s: opened %s at %d baud", self.id, port, baud_rate)
                    self._healthy = True
                    self._inner_loop(ser)
            except serial.SerialException as exc:
                self._healthy = False
                log.warning("%s: serial error — %s — retrying in 2s", self.id, exc)
                self._stop_event.wait(2)

        self._healthy = False

    def _inner_loop(self, ser: serial.Serial) -> None:
        while not self._stop_event.is_set():
            # Sync to frame header 0x59 0x59
            b = ser.read(1)
            if not b or b[0] != 0x59:
                continue
            b2 = ser.read(1)
            if not b2 or b2[0] != 0x59:
                continue
            rest = ser.read(7)
            if len(rest) < 7:
                continue

            result = parse_frame(bytes([0x59, 0x59]) + rest)
            if result is None:
                continue

            dist_cm, strength, temp_c = result
            reading = SensorReading(
                sensor_id=self.id,
                sensor_type="tf_mini",
                timestamp=time.time(),
                data={
                    "distance_mm": dist_cm * 10,
                    "strength":    strength,
                    "temp_c":      round(temp_c, 1),
                },
            )
            self._broadcast(reading)
