from __future__ import annotations

from core.analog_array import AnalogArrayBase
from core.registry import register
from sensors.mq_array.driver import ADC_MAX, rs_over_r0


@register("mq_array")
class MqArray(AnalogArrayBase):
    """An array of MQ-series gas sensors, read as raw ADC over an MCU uplink.

    Wiring (which gas is on which channel) and per-unit calibration live in the
    sensor's `channels` config — authored consistently with the MCU's forge
    contract (config/mcus/<id>.yaml). Raw counts are always emitted; when a
    channel's calibration is {type: mq, rl, r0} we also emit its Rs/R0 ratio.
    """

    sensor_type = "mq_array"

    def enrich(self, data: dict, raw: dict[str, int]) -> None:
        ratios: dict[str, float] = {}
        for ch in self.config.channels:
            cal = ch.calibration or {}
            if cal.get("type") != "mq" or ch.signal not in raw:
                continue
            ratio = rs_over_r0(
                raw[ch.signal],
                float(cal.get("rl", 0.0)),
                float(cal.get("r0", 0.0)),
                int(cal.get("adc_max", ADC_MAX)),
            )
            if ratio is not None:
                ratios[ch.signal] = round(ratio, 4)
        if ratios:
            data["ratio"] = ratios
