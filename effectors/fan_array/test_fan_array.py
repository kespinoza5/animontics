"""Unit tests for the fan_array effector — per-fan min_duty (no hardware)."""
from __future__ import annotations

from core.mcu_link import CMD_SET_DUTY
from core.models import EffectorChannel, EffectorConfig
from effectors.fan_array.effector import FanArray


class FakeDevice:
    def __init__(self):
        self.calls = []
    def send_command(self, cmd_id, args):
        self.calls.append((cmd_id, list(args)))
        return True


def _fans(params):
    cfg = EffectorConfig(
        id="chassis", type="fan_array", backend={"device": "d"}, params=params,
        channels=[EffectorChannel(name="intake", index=0),
                  EffectorChannel(name="exhaust", index=1)],
    )
    e = FanArray("chassis", cfg)
    fake = FakeDevice()
    e.attach_devices({"d": fake})
    return e, fake


def test_per_fan_min_duty_overrides_default():
    e, fake = _fans({"min_duty": 0.3, "per_fan": {"exhaust": 0.5}})
    e.handle_request({"levels": {"intake": 0.5, "exhaust": 0.5}})
    assert (CMD_SET_DUTY, [0, 166]) in fake.calls    # intake floor 0.3 → (0.3+0.7*0.5)*255
    assert (CMD_SET_DUTY, [1, 191]) in fake.calls    # exhaust floor 0.5 → (0.5+0.5*0.5)*255


def test_falls_back_to_default_floor_and_off():
    e, fake = _fans({"min_duty": 0.2})
    e.handle_request({"levels": {"intake": 0.0}})    # 0 → fully off
    assert (CMD_SET_DUTY, [0, 0]) in fake.calls
    e.handle_request({"levels": {"intake": 1.0}})
    assert (CMD_SET_DUTY, [0, 255]) in fake.calls


def test_descriptor():
    e, _ = _fans({"min_duty": 0.3, "per_fan": {"exhaust": 0.5}})
    d = e.descriptor()
    assert d["type"] == "fan_array"
    assert d["per_fan"] == {"exhaust": 0.5}
    assert d["min_duty"] == 0.3
