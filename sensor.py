from __future__ import annotations

from core.analog_array import AnalogArrayBase
from core.registry import register
from sensors.pressure_array.driver import to_kpa


@register("pressure_array")
class PressureArray(AnalogArrayBase):
    """A logical pressure surface read across one or more MCU devices.

    The cranial-pressure surface spans 4 MCUs × 4 ADS1115 (64 channels) — each
    channel maps a (device, index) to a pressure signal. AnalogArrayBase composes
    the per-device frames into one reading; this adds a calibrated kPa value per
    channel whose calibration is `linear` (raw counts are always present).
    """

    sensor_type = "pressure_array"

    def enrich(self, data: dict, raw: dict[str, int]) -> None:
        kpa: dict[str, float] = {}
        for ch in self.config.channels:
            cal = ch.calibration or {}
            if cal.get("type") == "linear" and ch.signal in raw:
                kpa[ch.signal] = round(
                    to_kpa(raw[ch.signal], float(cal.get("scale", 1.0)),
                           float(cal.get("offset", 0.0))), 3
                )
        if kpa:
            data["kpa"] = kpa
