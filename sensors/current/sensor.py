from __future__ import annotations

from core.analog_array import AnalogArrayBase
from core.registry import register


@register("current")
class CurrentSensor(AnalogArrayBase):
    """Rail current from hall-effect sensors (ACS712 et al.) — interoception.

    Device-fed: the ACS712's analog output (Vcc/2 at zero current, ±mV/A)
    arrives as raw ADC counts over an `ads1115` device or MCU uplink. The
    counts→amps meaning lives here, per channel:

    Calibration `{type: acs712, zero_counts, counts_per_amp}`:
        amps = (count - zero_counts) / counts_per_amp        (signed)

    `zero_counts` is captured at bench with the load off (it drifts with the
    sensor's actual Vcc); `counts_per_amp` folds together the sensor's mV/A
    (66 for the 30 A part) and the ADC's counts/mV at the configured gain.
    The overcurrent guard observes the published `amps` signal — see
    policies/threshold.
    """

    sensor_type = "current"

    def enrich(self, data: dict, raw: dict[str, int]) -> None:
        amps: dict[str, float] = {}
        for ch in self.config.channels:
            cal = ch.calibration or {}
            if cal.get("type") != "acs712" or ch.signal not in raw:
                continue
            cpa = float(cal.get("counts_per_amp", 1.0)) or 1.0
            zero = float(cal.get("zero_counts", 0.0))
            amps[ch.signal] = round((raw[ch.signal] - zero) / cpa, 3)
        if amps:
            data["amps"] = amps
