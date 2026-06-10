from __future__ import annotations

import logging
import threading
import time

from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
import sensors.sara_r5_gnss.driver as _drv

log = logging.getLogger(__name__)


@register("sara_r5_gnss")
class SaraR5GnssSensor(SensorBase):
    """GNSS readings from the SARA-R5 modem's NMEA stream.

    Subscribes to the sara_r5 device's NMEA push callbacks — no UART port of
    its own. Config must list the sara_r5 device id under `devices:`.

    The sensor emits one reading per GGA sentence, merging any RMC fields
    accumulated in the same fix cycle (speed, heading, utc_time).
    """

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        self._device = None
        self._lock = threading.Lock()
        self._partial: dict = {}
        self._healthy = False

    # ── Device binding ────────────────────────────────────────────────────────

    def attach_devices(self, devices: dict) -> None:
        for dev_id in self.config.devices:
            device = devices.get(dev_id)
            if device is not None and hasattr(device, "subscribe_gnss"):
                self._device = device
                log.info("%s: bound to device %s", self.id, dev_id)
                return
        log.warning("%s: no sara_r5 device found in %s", self.id, self.config.devices)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._device is not None:
            self._device.subscribe_gnss(self._on_nmea)
            self._healthy = True
        else:
            log.warning("%s: no device — GNSS inactive", self.id)

    def stop(self) -> None:
        self._healthy = False

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy and self._latest is not None

    # ── NMEA callback (called from SaraR5Device's read thread) ───────────────

    def _on_nmea(self, line: str) -> None:
        parsed = _drv.parse_nmea_sentence(line)
        if not parsed:
            return

        with self._lock:
            self._partial.update(parsed)
            # Emit on every GGA (has fix_quality); GGA is the authoritative fix sentence.
            if "fix_quality" not in parsed:
                return
            data = dict(self._partial)

        # Ensure all expected keys are present even if one sentence was missing
        data.setdefault("latitude", None)
        data.setdefault("longitude", None)
        data.setdefault("fix_quality", None)
        data.setdefault("satellites", None)
        data.setdefault("hdop", None)
        data.setdefault("alt_m", None)
        data.setdefault("speed_kph", None)
        data.setdefault("heading_deg", None)
        data.setdefault("utc_time", None)
        data.setdefault("rmc_valid", None)

        reading = SensorReading(
            sensor_id=self.id,
            sensor_type="sara_r5_gnss",
            timestamp=time.time(),
            data=data,
        )
        self._broadcast(reading)
