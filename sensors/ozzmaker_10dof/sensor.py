from __future__ import annotations

import logging
import threading
import time

import smbus2

from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
import sensors.ozzmaker_10dof.driver_lsm6dsl as _imu
import sensors.ozzmaker_10dof.driver_mmc5983ma as _mag
from sensors.ozzmaker_10dof.driver_bmp388 import BMP388

log = logging.getLogger(__name__)

_SAMPLE_RATE_HZ = 50   # target loop rate (imu @ 104 Hz onboard; we read at 50 Hz)


@register("ozzmaker_10dof")
class OzzMaker10DofSensor(SensorBase):
    """OzzMaker LTE-M GPS + 10DOF — IMU + magnetometer + barometer over I2C.

    Reads three chips on the same I2C bus:
      LSM6DSL  @ 0x6A — 3-axis accel + 3-axis gyro
      MMC5983MA @ 0x30 — 3-axis magnetometer
      BMP388   @ 0x77 — pressure + temperature

    Config connection fields:
      type:    i2c
      bus:     3     (I2C bus number, e.g. /dev/i2c-3)

    Chip addresses are fixed silicon — not user-configurable.
    """

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._healthy = False

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name=f"sensor-{self.id}"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy

    def _loop(self) -> None:
        bus_num = (self.config.connection.bus if self.config.connection else None) or 3
        interval = 1.0 / _SAMPLE_RATE_HZ

        while not self._stop.is_set():
            try:
                bus = smbus2.SMBus(bus_num)
                _imu.init(bus)
                _mag.init(bus)
                baro = BMP388(bus)
                log.info("%s: 10DOF ready on i2c-%d", self.id, bus_num)
                self._healthy = True
                self._inner_loop(bus, baro, interval)
            except Exception as exc:
                self._healthy = False
                log.warning("%s: sensor error — %s — retrying in 3s", self.id, exc)
                self._stop.wait(3)
            finally:
                try:
                    bus.close()
                except Exception:
                    pass

        self._healthy = False

    def _inner_loop(self, bus, baro: BMP388, interval: float) -> None:
        # Barometer is read at a slower rate (~1 Hz) to avoid contention
        baro_counter = 0
        baro_period = max(1, round(1.0 / interval))
        baro_data: dict = {}

        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                imu_data = _imu.read(bus)
                mag_data = _mag.read(bus)
                if baro_counter == 0:
                    baro_data = baro.read()
                baro_counter = (baro_counter + 1) % baro_period

                data = {**imu_data, **mag_data, **baro_data}
                reading = SensorReading(
                    sensor_id=self.id,
                    sensor_type="ozzmaker_10dof",
                    timestamp=time.time(),
                    data=data,
                )
                self._broadcast(reading)
            except OSError as exc:
                self._healthy = False
                log.warning("%s: I2C read error — %s", self.id, exc)
                return   # reconnect from outer loop

            elapsed = time.monotonic() - t0
            sleep = interval - elapsed
            if sleep > 0:
                self._stop.wait(sleep)
