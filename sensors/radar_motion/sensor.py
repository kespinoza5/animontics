from __future__ import annotations

from core.analog_array import AnalogArrayBase
from core.registry import register


@register("radar_motion")
class RadarMotion(AnalogArrayBase):
    """Microwave Doppler motion from analog-hacked RCWL-0516 modules.

    The stock RCWL-0516 outputs a 2 s digital pulse; these units are hacked to
    expose the analog Doppler stage instead, so motion appears as deviation
    from a slowly-drifting resting level. Device-fed raw counts; meaning here:

    Per channel, a slow EMA baseline tracks the resting level and the reading
    publishes the absolute deviation plus a boolean over `params.threshold`:

        level  = |count - baseline|          (counts)
        motion = level > threshold

    Config keys (params):
        baseline_alpha — EMA coefficient for the resting level (default 0.02;
                         smaller = slower drift tracking)
        threshold      — counts of deviation that count as motion (default 500;
                         tune at bench — VERIFY against the hack's gain)

    The baseline only adapts while quiescent (level under threshold), so a
    person standing in the field doesn't get absorbed into "resting".
    """

    sensor_type = "radar_motion"

    def __init__(self, sensor_id, config) -> None:
        super().__init__(sensor_id, config)
        self._baseline: dict[str, float] = {}

    def enrich(self, data: dict, raw: dict[str, int]) -> None:
        p = self.config.params or {}
        alpha = float(p.get("baseline_alpha", 0.02))
        threshold = float(p.get("threshold", 500))
        level: dict[str, float] = {}
        motion: dict[str, bool] = {}
        for signal, count in raw.items():
            base = self._baseline.get(signal)
            if base is None:
                base = float(count)               # first sample seeds the baseline
            dev = abs(count - base)
            if dev <= threshold:                  # adapt only while quiescent
                base = base + alpha * (count - base)
            self._baseline[signal] = base
            level[signal] = round(dev, 1)
            motion[signal] = dev > threshold
        if level:
            data["level"] = level
            data["motion"] = motion
