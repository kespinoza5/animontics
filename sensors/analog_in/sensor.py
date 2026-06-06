from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from core.models import SensorReading
from core.registry import register
from core.sensor_base import SensorBase

if TYPE_CHECKING:
    from core.device import Device

log = logging.getLogger(__name__)


@register("analog_in")
class AnalogIn(SensorBase):
    """Heterogeneous scalar analog inputs read through a pull device (an ADS1115).

    Unlike an array sensor, each channel is its own *signal* with its own meaning
    and calibration (e.g. 4 different sources on one Pi02W ADS1115). Polls each
    configured channel via the device's read_channel(); emits raw counts always,
    plus a calibrated value per channel whose calibration is `linear`.
    """

    INTERVAL_S = 0.5

    def __init__(self, sensor_id, config) -> None:
        super().__init__(sensor_id, config)
        self._devices: dict[str, "Device"] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._healthy = False

    @property
    def device_ids(self) -> set[str]:
        return {ch.device for ch in self.config.channels if ch.device}

    def attach_devices(self, devices: dict[str, "Device"]) -> None:
        missing = self.device_ids - set(devices)
        if missing:
            raise ValueError(f"sensor '{self.id}': unknown device(s) {sorted(missing)}")
        self._devices = {d: devices[d] for d in self.device_ids}

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

    def _read_once(self) -> SensorReading | None:
        """Poll every channel once. Returns a reading, or None if nothing read."""
        data: dict = {"raw": {}}
        for ch in self.config.channels:
            device = self._devices.get(ch.device)
            cal = ch.calibration or {}
            raw = device.read_channel(ch.index, int(cal.get("gain", 1))) if device else None
            if raw is None:
                continue
            data["raw"][ch.signal] = raw
            if cal.get("type") == "linear":
                data[ch.signal] = round(
                    raw * float(cal.get("scale", 1.0)) + float(cal.get("offset", 0.0)), 4
                )
        if not data["raw"]:
            return None
        return SensorReading(sensor_id=self.id, sensor_type="analog_in",
                             timestamp=time.time(), data=data)

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            reading = self._read_once()
            self._healthy = reading is not None
            if reading is not None:
                self._broadcast(reading)
            self._stop_event.wait(self.INTERVAL_S)
        self._healthy = False
