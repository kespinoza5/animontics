from __future__ import annotations

import array
import logging
import struct
import sys
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

# Binary frame layout (little-endian), consumed by web/viewers/mlx90640.html:
#   offset 0   uint32   frame_id   (monotonic, lets the client drop dupes)
#   offset 4   float32  min_temp °C
#   offset 8   float32  max_temp °C
#   offset 12  float32 × 768  pixels, row-major 32×24, °C
# Total = 12 + 768*4 = 3084 bytes.
_FRAME_HEADER = struct.Struct("<Iff")
_LITTLE_ENDIAN = sys.byteorder == "little"


@register("mlx90640")
class MLX90640Sensor(SensorBase):
    """
    Melexis MLX90640 32×24 IR thermal array over I2C.

    Config connection fields:
      type:    i2c
      bus:     3       (I2C bus number)
      address: 0x33    (default MLX90640 address)

    Two output lanes:
      JSON reading (/sensors/<id>/stream, /ws) — lean per-frame summary:
        {min_temp, max_temp, width, height}. No pixel array, so serialising it
        32×/s stays cheap and GET /sensors/<id> is a light snapshot.
      Binary frames (/sensors/<id>/frames) — the full 768-pixel array as a
        packed little-endian frame (see _FRAME_HEADER above). This is the lane
        the thermal viewer consumes; it skips json.dumps server-side and a big
        array parse + GC client-side.
    """

    produces_frames = True

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._healthy = False
        self._frame_id = 0

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

                # Binary lane: full array, packed once at C speed (no per-float
                # Python call). byteswap only on the rare big-endian host.
                self._frame_id = (self._frame_id + 1) & 0xFFFFFFFF
                pix = array.array("f", buf)
                if not _LITTLE_ENDIAN:
                    pix.byteswap()
                self._broadcast_frame(
                    _FRAME_HEADER.pack(self._frame_id, mn, mx) + pix.tobytes()
                )

                # JSON lane: lean summary only — the array lives on /frames.
                reading = SensorReading(
                    sensor_id=self.id,
                    sensor_type="mlx90640",
                    timestamp=time.time(),
                    data={
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
