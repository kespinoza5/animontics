from __future__ import annotations

from core.analog_array import AnalogArrayBase
from core.registry import register


@register("servo_feedback")
class ServoFeedback(AnalogArrayBase):
    """Proprioception: servo pot-wiper taps read back as joint angles.

    Device-fed (no `connection`): channels arrive over an MCU serial uplink
    (e.g. the cervical SAMD21's `analog_in` pins) or an SBC-side ADS1115 (the
    ear pots on the pizero). The taps are voltage-divided to the ADC rail —
    the divider ratio is *part of the calibration end points*, never firmware.

    Calibration `{type: servo_pot, counts_min, counts_max, deg_min, deg_max}`:
        deg = deg_min + (count - counts_min) / (counts_max - counts_min)
                      * (deg_max - deg_min),   clamped to [deg_min, deg_max]
    Endpoints are measured at bench (command the servo to each soft limit and
    record the counts). Raw counts are always emitted alongside.
    """

    sensor_type = "servo_feedback"

    def enrich(self, data: dict, raw: dict[str, int]) -> None:
        deg: dict[str, float] = {}
        for ch in self.config.channels:
            cal = ch.calibration or {}
            if cal.get("type") != "servo_pot" or ch.signal not in raw:
                continue
            lo = float(cal.get("counts_min", 0))
            hi = float(cal.get("counts_max", 32767))
            d0 = float(cal.get("deg_min", 0.0))
            d1 = float(cal.get("deg_max", 180.0))
            span = (hi - lo) or 1.0
            frac = (raw[ch.signal] - lo) / span
            deg[ch.signal] = round(max(d0, min(d1, d0 + frac * (d1 - d0))), 2)
        if deg:
            data["deg"] = deg
