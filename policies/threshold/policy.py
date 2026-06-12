from __future__ import annotations

from core.policy import PolicyBase, register_policy


@register_policy("threshold")
class ThresholdPolicy(PolicyBase):
    """A guard reflex: trip an effector off when a signal crosses a bound.

    Instantiated as the overcurrent guard (ACS712 amps → servo power rail), but
    generic: any observed signal, any on/off effector driven over the levels
    lane (1.0 = armed/on, 0.0 = tripped/off).

    Config keys (params):
        trip_above     — trip when ANY observed signal exceeds this
        release_below  — re-arm only when ALL signals fall below this
                         (hysteresis: keep well under trip_above)
        latch          — true: once tripped, stay tripped until the policy is
                         disabled/re-enabled or the node restarts (default false)

    Behavior notes, deliberate:
      - Emits an action ONLY on state transitions (trip / release). A guard
        that re-asserts "on" every tick would fight manual rail control via
        the effector API; returning {} between transitions leaves the rail
        alone (PolicyRuntime skips empty actions).
      - Missing observations never trip (an absent sensor is not an
        emergency) — but they also never release.
    """

    SPEC = {
        "description": "Trip/release guard — drives an effector when a signal crosses a threshold.",
        "needs_effector": True,
        "needs_observation": True,
        "params": ["trip_above", "release_below", "latch"],
    }

    def __init__(self, policy_id, config) -> None:
        super().__init__(policy_id, config)
        self._tripped = False

    @property
    def tripped(self) -> bool:
        return self._tripped

    def step(self, obs: dict) -> dict:
        p = self.config.params
        trip_above = float(p.get("trip_above", float("inf")))
        release_below = float(p.get("release_below", trip_above))
        latch = bool(p.get("latch", False))

        values = [float(v) for v in obs.values() if v is not None]
        if not values:
            return {}

        if not self._tripped and any(v > trip_above for v in values):
            self._tripped = True
            return {ch: 0.0 for ch in self._target_channels}

        if self._tripped and not latch and all(v < release_below for v in values):
            self._tripped = False
            return {ch: 1.0 for ch in self._target_channels}

        return {}
