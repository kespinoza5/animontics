"""Unit tests for the curve policy — max-linear reflex (no hardware)."""
from __future__ import annotations

from core.models import EffectorChannel, PolicyConfig
from policies.curve.policy import CurvePolicy


class FakeEffector:
    def __init__(self, names):
        self.channels = [EffectorChannel(name=n, index=i) for i, n in enumerate(names)]


def _curve(observation, params, channels):
    cfg = PolicyConfig(id="fan", type="curve", always_on=True, observation=observation,
                       action={"effector": "fans"}, params=params)
    p = CurvePolicy("fan", cfg)
    p.bind_effector(FakeEffector(channels))
    return p


def test_max_linear_over_inputs():
    p = _curve(["gas.x", "temp.c"],
               {"in_min": [0, 20], "in_max": [100, 60], "out_min": 0.2, "out_max": 1.0},
               ["intake", "exhaust"])
    # gas norm .5, temp norm 1.0 → max 1.0 → drive 1.0 on every channel
    assert p.step({"gas.x": 50, "temp.c": 60}) == {"intake": 1.0, "exhaust": 1.0}
    # both at floor → out_min
    assert p.step({"gas.x": 0, "temp.c": 20}) == {"intake": 0.2, "exhaust": 0.2}


def test_missing_input_is_failsafe_low():
    p = _curve(["gas.x"], {"in_min": [0], "in_max": [100], "out_min": 0.2, "out_max": 1.0}, ["a"])
    assert p.step({}) == {"a": 0.2}          # absent sensor never forces high output
