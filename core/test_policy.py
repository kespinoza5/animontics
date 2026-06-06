"""Unit tests for the relay + policy tier — curve reflex + runtime (no hardware)."""
from __future__ import annotations

from core.models import EffectorChannel, PolicyConfig, SensorReading
from core.policy import CurvePolicy, PolicyRuntime
from core.relay import Relay


class FakeEffector:
    def __init__(self, names):
        self.channels = [EffectorChannel(name=n, index=i) for i, n in enumerate(names)]
        self.requests = []
    def handle_request(self, payload):
        self.requests.append(payload)
        return {"set": {}}


class FakeSensor:
    def __init__(self, data):
        self.latest = SensorReading(sensor_id="s", sensor_type="t", timestamp=0.0, data=data)


# ── Relay ─────────────────────────────────────────────────────────────────────

class TestRelay:
    def test_publish_latest(self):
        r = Relay()
        r.publish("a.b", 5)
        assert r.latest("a.b") == 5
        assert r.latest("missing", -1) == -1

    def test_publish_tree_flattens(self):
        r = Relay()
        r.publish_tree("gas", {"seq": 1, "raw": {"mq135": 400}})
        assert r.latest("gas.seq") == 1
        assert r.latest("gas.raw.mq135") == 400

    def test_gate_can_drop(self):
        r = Relay(gate=lambda name, value: None if name == "block" else value)
        r.publish("block", 1)
        r.publish("ok", 2)
        assert r.latest("block") is None
        assert r.latest("ok") == 2


# ── CurvePolicy ───────────────────────────────────────────────────────────────

def _curve(observation, params, channels):
    cfg = PolicyConfig(id="fan", type="curve", always_on=True, observation=observation,
                       action={"effector": "fans"}, params=params)
    p = CurvePolicy("fan", cfg)
    p.bind_effector(FakeEffector(channels))
    return p


class TestCurvePolicy:
    def test_max_linear_over_inputs(self):
        p = _curve(["gas.x", "temp.c"],
                   {"in_min": [0, 20], "in_max": [100, 60], "out_min": 0.2, "out_max": 1.0},
                   ["intake", "exhaust"])
        # gas norm .5, temp norm 1.0 → max 1.0 → drive 1.0 on every channel
        assert p.step({"gas.x": 50, "temp.c": 60}) == {"intake": 1.0, "exhaust": 1.0}
        # both at floor → out_min
        assert p.step({"gas.x": 0, "temp.c": 20}) == {"intake": 0.2, "exhaust": 0.2}

    def test_missing_input_is_failsafe_low(self):
        p = _curve(["gas.x"], {"in_min": [0], "in_max": [100], "out_min": 0.2, "out_max": 1.0}, ["a"])
        assert p.step({}) == {"a": 0.2}      # absent sensor never forces high output


# ── PolicyRuntime ─────────────────────────────────────────────────────────────

def _runtime(policy, sensors, effectors):
    return PolicyRuntime([policy], sensors, effectors, Relay())


class TestPolicyRuntime:
    def test_tick_reads_sensor_and_drives_effector(self):
        sensor = FakeSensor({"raw": {"mq135": 100}})
        eff = FakeEffector(["intake"])
        cfg = PolicyConfig(id="fan", type="curve", always_on=True,
                           observation=["gas.raw.mq135"], action={"effector": "fans"},
                           params={"in_min": [0], "in_max": [100], "out_min": 0.0, "out_max": 1.0})
        rt = PolicyRuntime([CurvePolicy("fan", cfg)], {"gas": sensor}, {"fans": eff}, Relay())
        rt.tick()
        assert eff.requests[-1] == {"levels": {"intake": 1.0}}     # mq135=100 → drive 1.0
        assert rt.policies[0].last_action == {"intake": 1.0}

    def test_disabled_policy_skipped(self):
        sensor = FakeSensor({"raw": {"mq135": 100}})
        eff = FakeEffector(["intake"])
        cfg = PolicyConfig(id="fan", type="curve", observation=["gas.raw.mq135"],
                           action={"effector": "fans"},
                           params={"in_min": [0], "in_max": [100], "out_min": 0.0, "out_max": 1.0})
        p = CurvePolicy("fan", cfg)
        p.enabled = False
        rt = PolicyRuntime([p], {"gas": sensor}, {"fans": eff}, Relay())
        rt.tick()
        assert eff.requests == []

    def test_always_on_ordered_first(self):
        cortical = CurvePolicy("c", PolicyConfig(id="c", type="curve", always_on=False))
        reflex = CurvePolicy("r", PolicyConfig(id="r", type="curve", always_on=True))
        rt = PolicyRuntime([cortical, reflex], {}, {}, Relay())
        assert rt.policies[0].id == "r"
