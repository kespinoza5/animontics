from __future__ import annotations

import logging
import threading
import time

import serial

from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
from sensors.lv_maxsonar.driver import parse_line

log = logging.getLogger(__name__)

_INCHES_TO_MM = 25.4


@register("lv_maxsonar")
class LVMaxSonarSensor(SensorBase):
    """
    MaxBotix LV-MaxSonar-EZ ultrasonic distance sensor over UART.

    Config connection fields:
      type:      uart
      port:      /dev/ttyS0
      baud_rate: 9600
    """

    BAUD_DEFAULT = 9_600

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
        port      = self.config.connection.port or "/dev/ttyS0"
        baud_rate = self.config.connection.baud_rate or self.BAUD_DEFAULT

        while not self._stop_event.is_set():
            try:
                with serial.Serial(port, baud_rate, timeout=2) as ser:
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
            raw = ser.read_until(b"\r")
            if not raw:
                continue
            inches = parse_line(raw)
            if inches is None:
                continue
            distance_mm = round(inches * _INCHES_TO_MM)
            reading = SensorReading(
                sensor_id=self.id,
                sensor_type="lv_maxsonar",
                timestamp=time.time(),
                data={
                    "distance_mm": distance_mm,
                    "strength":    None,
                    "temp_c":      None,
                },
            )
            self._broadcast(reading)
