from __future__ import annotations

import logging
import threading
import time

import smbus2

from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
from sensors.mlx90640.driver import MLX90640

log = logging.getLogger(__name__)

_WIDTH  = 32
_HEIGHT = 24
_PIXELS = _WIDTH * _HEIGHT


@register("mlx90640")
class MLX90640Sensor(SensorBase):
    """
    Melexis MLX90640 32×24 IR thermal array over I2C.

    Config connection fields:
      type:    i2c
      bus:     3       (I2C bus number)
      address: 0x33    (default MLX90640 address)

    SensorReading data keys:
      pixels:   list[float]  (768 values, row-major 32×24, °C)
      min_temp: float
      max_temp: float
      width:    int (32)
      height:   int (24)
    """

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
            self._thread.join(timeout=5)

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy

    # ── Background reading loop ───────────────────────────────────────────────

    def _read_loop(self) -> None:
        bus_num = self.config.connection.bus if self.config.connection.bus is not None else 3
        addr    = self.config.connection.address or 0x33

        while not self._stop_event.is_set():
            try:
                bus    = smbus2.SMBus(bus_num)
                sensor = MLX90640(bus, addr)
                log.info("%s: MLX90640 ready on i2c-%d addr=0x%02X", self.id, bus_num, addr)
                self._healthy = True
                self._inner_loop(sensor)
            except Exception as exc:
                self._healthy = False
                log.warning("%s: sensor error — %s — retrying in 3s", self.id, exc)
                self._stop_event.wait(3)

        self._healthy = False

    def _inner_loop(self, sensor: MLX90640) -> None:
        buf = [20.0] * _PIXELS
        while not self._stop_event.is_set():
            try:
                sensor.get_frame(buf)
                mn = min(buf)
                mx = max(buf)
                reading = SensorReading(
                    sensor_id=self.id,
                    sensor_type="mlx90640",
                    timestamp=time.time(),
                    data={
                        "pixels":   [round(v, 2) for v in buf],
                        "min_temp": round(mn, 2),
                        "max_temp": round(mx, 2),
                        "width":    _WIDTH,
                        "height":   _HEIGHT,
                    },
                )
                self._broadcast(reading)
            except Exception as exc:
                log.error("%s: frame error — %s", self.id, exc)
                time.sleep(0.5)
