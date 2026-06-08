"""Unit tests for the pwm effector — drive, min_duty, registry (no hardware)."""
from __future__ import annotations

import pytest

from core.effector_base import create_effector
from core.mcu_link import CMD_SET_DUTY
from core.models import EffectorChannel, EffectorConfig
from effectors.pwm.effector import PwmEffector


class FakeDevice:
    def __init__(self):
        self.calls = []
    def send_command(self, cmd_id, args):
        self.calls.append((cmd_id, list(args)))
        return True


def _pwm(params=None):
    cfg = EffectorConfig(
        id="fans", type="pwm", backend={"device": "d"}, params=params or {},
        channels=[EffectorChannel(name="intake", index=0),
                  EffectorChannel(name="exhaust", index=1)],
    )
    e = PwmEffector("fans", cfg)
    fake = FakeDevice()
    e.attach_devices({"d": fake})
    return e, fake


class TestDrive:
    def test_by_name_scaled(self):
        e, fake = _pwm()
        e.handle_request({"levels": {"intake": 1.0, "exhaust": 0.5}})
        assert (CMD_SET_DUTY, [0, 255]) in fake.calls
        assert (CMD_SET_DUTY, [1, 128]) in fake.calls

    def test_by_index_key(self):
        e, fake = _pwm()
        e.handle_request({"levels": {0: 0.0}})
        assert (CMD_SET_DUTY, [0, 0]) in fake.calls

    def test_bare_dict(self):
        e, fake = _pwm()
        e.handle_request({"intake": 0.2})
        assert fake.calls[0][1][0] == 0

    def test_unknown_channel(self):
        e, _ = _pwm()
        assert e.handle_request({"levels": {"nope": 0.5}})["set"]["nope"] == "unknown channel"

    def test_link_down_without_device(self):
        cfg = EffectorConfig(id="f", type="pwm", channels=[EffectorChannel(name="a", index=0)])
        assert PwmEffector("f", cfg).handle_request({"levels": {"a": 1.0}})["set"]["a"] == "link down"

    def test_descriptor(self):
        d, _ = _pwm()
        desc = d.descriptor()
        assert desc["type"] == "pwm" and desc["value"] == "0.0-1.0"
        assert {c["name"] for c in desc["channels"]} == {"intake", "exhaust"}


class TestMinDuty:
    def test_zero_is_off(self):
        e, fake = _pwm({"min_duty": 0.3})
        e.handle_request({"levels": {"intake": 0.0}})
        assert (CMD_SET_DUTY, [0, 0]) in fake.calls

    def test_nonzero_maps_into_floor(self):
        e, fake = _pwm({"min_duty": 0.3})
        e.handle_request({"levels": {"intake": 0.5}})       # (0.3 + 0.7*0.5)*255
        assert (CMD_SET_DUTY, [0, 166]) in fake.calls

    def test_full_is_max(self):
        e, fake = _pwm({"min_duty": 0.3})
        e.handle_request({"levels": {"intake": 1.0}})
        assert (CMD_SET_DUTY, [0, 255]) in fake.calls

    def test_default_no_floor(self):
        e, fake = _pwm()
        e.handle_request({"levels": {"intake": 0.5}})
        assert (CMD_SET_DUTY, [0, 128]) in fake.calls

    def test_descriptor_reports_min_duty(self):
        e, _ = _pwm({"min_duty": 0.3})
        assert e.descriptor()["min_duty"] == 0.3


def test_create_effector_unknown_type():
    with pytest.raises(ValueError):
        create_effector(EffectorConfig(id="x", type="bogus"))
