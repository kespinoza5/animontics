from __future__ import annotations

import logging
import threading
import time

import smbus2

from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
from sensors.vl53l1x.driver import VL53L1X

log = logging.getLogger(__name__)


@register("vl53l1x")
class VL53L1XSensor(SensorBase):
    """
    ST VL53L1X time-of-flight distance sensor over I2C.

    Config connection fields:
      type:    i2c
      bus:     3         (I2C bus number, e.g. /dev/i2c-3)
      address: 0x29      (default VL53L1X address)

    The sensor starts in long-range mode (mode 3, ~4 m). Auto-ranging between
    short/medium/long modes is available via set_mode() calls on the sensor
    object — future API endpoint can expose this.
    """

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._healthy = False
        self._mode = 3  # long range default

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

    # ── Background reading loop ───────────────────────────────────────────────

    def _read_loop(self) -> None:
        bus_num = self.config.connection.bus if self.config.connection.bus is not None else 3
        addr    = self.config.connection.address or 0x29

        while not self._stop_event.is_set():
            try:
                bus    = smbus2.SMBus(bus_num)
                sensor = VL53L1X(bus, addr)
                sensor.init()
                if self._mode != 3:
                    sensor.set_distance_mode(self._mode)
                sensor.start_continuous()
                log.info("%s: VL53L1X ready on i2c-%d addr=0x%02X mode=%d",
                         self.id, bus_num, addr, self._mode)
                self._healthy = True
                self._inner_loop(sensor)
            except Exception as exc:
                self._healthy = False
                log.warning("%s: sensor error — %s — retrying in 3s", self.id, exc)
                self._stop_event.wait(3)

        self._healthy = False

    def _inner_loop(self, sensor: VL53L1X) -> None:
        while not self._stop_event.is_set():
            mm = sensor.read_mm(timeout=0.2)
            reading = SensorReading(
                sensor_id=self.id,
                sensor_type="vl53l1x",
                timestamp=time.time(),
                data={
                    "distance_mm": mm,
                    "strength":    None,
                    "temp_c":      None,
                },
            )
            self._broadcast(reading)
