from __future__ import annotations

import glob
import logging
import threading
import time

from core.models import SensorReading
from core.registry import register
from core.sensor_base import SensorBase

log = logging.getLogger(__name__)


@register("board_temp")
class BoardTemp(SensorBase):
    """SBC board/CPU temperatures from Linux thermal zones (sysfs).

    No external hardware and no device — reads /sys/class/thermal/thermal_zone*/temp.
    Emits one key per zone (zone0_c, zone1_c, …) plus `cpu_c` (the primary, zone0).
    A common input to a cooling-control policy.
    """

    ZONES = "/sys/class/thermal/thermal_zone*/temp"
    INTERVAL_S = 2.0

    def __init__(self, sensor_id, config) -> None:
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

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            data: dict = {}
            for i, zone in enumerate(sorted(glob.glob(self.ZONES))):
                try:
                    with open(zone) as fh:
                        data[f"zone{i}_c"] = round(int(fh.read().strip()) / 1000.0, 1)
                except (OSError, ValueError):
                    continue
            if data:
                data["cpu_c"] = data.get("zone0_c")
                self._healthy = True
                self._broadcast(SensorReading(
                    sensor_id=self.id, sensor_type="board_temp",
                    timestamp=time.time(), data=data,
                ))
            else:
                self._healthy = False          # no thermal zones (e.g. non-Linux dev box)
            self._stop_event.wait(self.INTERVAL_S)
        self._healthy = False
