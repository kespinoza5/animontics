from __future__ import annotations

import logging
import threading
import time

from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
import sensors.sara_r5_lte.driver as _drv

log = logging.getLogger(__name__)

_POLL_INTERVAL = 30  # seconds between LTE status refreshes


@register("sara_r5_lte")
class SaraR5LteSensor(SensorBase):
    """LTE signal quality and registration status from the SARA-R5 modem.

    Polls the sara_r5 device via AT commands every 30 seconds. Config must list
    the sara_r5 device id under `devices:`.
    """

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        self._device = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._healthy = False

    # ── Device binding ────────────────────────────────────────────────────────

    def attach_devices(self, devices: dict) -> None:
        for dev_id in self.config.devices:
            device = devices.get(dev_id)
            if device is not None and hasattr(device, "send_at"):
                self._device = device
                log.info("%s: bound to device %s", self.id, dev_id)
                return
        log.warning("%s: no sara_r5 device found in %s", self.id, self.config.devices)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name=f"sensor-{self.id}"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy

    # ── Polling loop ──────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._device is None or not self._device.is_healthy():
                self._healthy = False
                self._stop.wait(5)
                continue
            try:
                data = _drv.query_lte_status(self._device.send_at)
                reading = SensorReading(
                    sensor_id=self.id,
                    sensor_type="sara_r5_lte",
                    timestamp=time.time(),
                    data=data,
                )
                self._broadcast(reading)
                self._healthy = True
            except Exception as exc:
                self._healthy = False
                log.warning("%s: LTE poll error — %s", self.id, exc)
            self._stop.wait(_POLL_INTERVAL)
