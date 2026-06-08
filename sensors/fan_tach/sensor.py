from __future__ import annotations

from core.analog_array import AnalogArrayBase
from core.registry import register


@register("fan_tach")
class FanTach(AnalogArrayBase):
    """Fan RPM streamed from an MCU's tach (FG) counters.

    A thin AnalogArrayBase: the device already streams RPM (the firmware `tach`
    module counts FG edges and converts), so the raw frame value *is* the RPM —
    no calibration. `enrich` just mirrors `raw` under `rpm` for a friendly key.
    """

    sensor_type = "fan_tach"

    def enrich(self, data: dict, raw: dict[str, int]) -> None:
        data["rpm"] = dict(raw)
