"""Unit tests for the threshold guard policy (no hardware)."""
from __future__ import annotations

from core.models import PolicyConfig
from core.policy import create_policy
from policies.threshold.policy import ThresholdPolicy


class FakeEffector:
    def __init__(self):
        from core.models import EffectorChannel
        self.channels = [EffectorChannel(name="main", index=0)]


def _policy(params=None):
    cfg = PolicyConfig(
        id="guard", type="threshold", always_on=True,
        observation=["rail_current.amps.servo_rail"],
        action={"effector": "servo_rail"},
        params=params or {"trip_above": 8.0, "release_below": 0.5},
    )
    p = create_policy(cfg)
    p.bind_effector(FakeEffector())
    return p


SIG = "rail_current.amps.servo_rail"


def test_trips_above_and_releases_below():
    p = _policy()
    assert p.step({SIG: 2.0}) == {}                 # nominal: no action
    assert p.step({SIG: 9.5}) == {"main": 0.0}      # trip
    assert p.tripped
    assert p.step({SIG: 6.0}) == {}                 # hysteresis band: hold
    assert p.step({SIG: 0.2}) == {"main": 1.0}      # release
    assert not p.tripped


def test_transitions_only_no_repeat_actions():
    p = _policy()
    assert p.step({SIG: 9.0}) == {"main": 0.0}
    assert p.step({SIG: 9.0}) == {}                 # still tripped: silent
    assert p.step({SIG: 0.1}) == {"main": 1.0}
    assert p.step({SIG: 0.1}) == {}                 # still armed: silent


def test_latch_never_releases():
    p = _policy({"trip_above": 8.0, "release_below": 0.5, "latch": True})
    assert p.step({SIG: 9.0}) == {"main": 0.0}
    assert p.step({SIG: 0.0}) == {}                 # latched: stays off
    assert p.tripped


def test_missing_observation_never_trips_or_releases():
    p = _policy()
    assert p.step({SIG: None}) == {}
    p.step({SIG: 9.0})                              # trip
    assert p.step({SIG: None}) == {}                # absent sensor: hold state
    assert p.tripped


def test_registry_type():
    assert isinstance(_policy(), ThresholdPolicy)
