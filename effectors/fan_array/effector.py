from __future__ import annotations

from core.effector_base import register_effector
from effectors.pwm.effector import PwmEffector


@register_effector("fan_array")
class FanArray(PwmEffector):
    """One or more named fans driven over the request lane.

    Built on the generic `pwm` drive (level 0–1 → device `set_duty`), adding what's
    fan-specific:

      - **per-fan `min_duty`** — fans differ in where they actually start;
        `params.per_fan: {<name>: <min_duty>}` overrides the effector-wide
        `params.min_duty` for that fan.

    RPM stays out here: a paired `fan_tach` sensor publishes RPM to the relay, and
    closing the loop (target RPM → trim level) is a *policy*, not the effector.
    """

    effector_type = "fan_array"

    SPEC = {
        "description": "Named fans over the request lane — per-fan min_duty atop pwm.",
        "backends": {"mcu": ["device"]},
        "default_backend": "mcu",
        "params": ["min_duty", "per_fan"],
    }

    def _min_duty_for(self, channel_name: str) -> float:
        per_fan = self.config.params.get("per_fan", {}) or {}
        if channel_name in per_fan:
            return max(0.0, min(1.0, float(per_fan[channel_name])))
        return self._default_min_duty

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["type"] = "fan_array"
        d["per_fan"] = self.config.params.get("per_fan", {})
        return d
