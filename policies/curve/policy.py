from __future__ import annotations

from core.policy import PolicyBase, register_policy


@register_policy("curve")
class CurvePolicy(PolicyBase):
    """A reflex: drive every target channel by a curve over normalized inputs.

    params: in_min[], in_max[] (aligned with `observation`), out_min, out_max.
    kind "max_linear" (default): drive = out_min + (out_max-out_min) *
    max_i clamp((x_i - in_min_i)/(in_max_i - in_min_i), 0, 1). Missing inputs are
    ignored (fail-safe: an absent sensor never forces high output).
    """

    SPEC = {
        "description": "Piecewise-linear map: observations → one effector's channels.",
        "needs_effector": True,
        "needs_observation": True,
        "params": ["in_min", "in_max", "out_min", "out_max"],
    }

    def step(self, obs: dict) -> dict:
        p = self.config.params
        in_min = p.get("in_min", [])
        in_max = p.get("in_max", [])
        out_min = float(p.get("out_min", 0.0))
        out_max = float(p.get("out_max", 1.0))

        norms: list[float] = []
        for i, name in enumerate(self.observation_names):
            value = obs.get(name)
            if value is None or i >= len(in_min) or i >= len(in_max):
                continue
            lo, hi = float(in_min[i]), float(in_max[i])
            if hi == lo:
                continue
            norms.append(max(0.0, min(1.0, (float(value) - lo) / (hi - lo))))

        drive = out_min + (out_max - out_min) * (max(norms) if norms else 0.0)
        drive = round(max(out_min, min(out_max, drive)), 4)
        return {ch: drive for ch in self._target_channels}
