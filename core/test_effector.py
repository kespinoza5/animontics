"""Unit tests for the effector tier — pwm request lane + stream lane (no hardware)."""
from __future__ import annotations

import pytest

from core.effector_base import PwmEffector, create_effector
from core.mcu_link import CMD_SET_DUTY
from core.models import EffectorChannel, EffectorConfig


class FakeDevice:
    def __init__(self):
        self.calls = []
    def send_command(self, cmd_id, args):
        self.calls.append((cmd_id, list(args)))
        return True


def _pwm():
    cfg = EffectorConfig(
        id="fans", type="pwm", backend={"device": "larduino"},
        channels=[EffectorChannel(name="intake", index=0),
                  EffectorChannel(name="exhaust", index=1)],
    )
    e = PwmEffector("fans", cfg)
    fake = FakeDevice()
    e.attach_devices({"larduino": fake})
    return e, fake


class TestPwm:
    def test_drives_by_name_scaled_to_255(self):
        e, fake = _pwm()
        e.handle_request({"levels": {"intake": 1.0, "exhaust": 0.5}})
        assert (CMD_SET_DUTY, [0, 255]) in fake.calls
        assert (CMD_SET_DUTY, [1, 128]) in fake.calls      # round(0.5*255)
        assert e.state()["intake"] == 1.0

    def test_drives_by_index_key(self):
        e, fake = _pwm()
        e.handle_request({"levels": {0: 0.0}})
        assert (CMD_SET_DUTY, [0, 0]) in fake.calls

    def test_bare_dict_without_levels_key(self):
        e, fake = _pwm()
        e.handle_request({"intake": 0.2})
        assert fake.calls[0][1][0] == 0                     # channel index 0

    def test_unknown_channel_reported(self):
        e, _ = _pwm()
        res = e.handle_request({"levels": {"nope": 0.5}})
        assert res["set"]["nope"] == "unknown channel"

    def test_link_down_when_no_device(self):
        cfg = EffectorConfig(id="fans", type="pwm",
                             channels=[EffectorChannel(name="a", index=0)])
        e = PwmEffector("fans", cfg)                        # no device attached
        assert e.handle_request({"levels": {"a": 1.0}})["set"]["a"] == "link down"

    def test_descriptor(self):
        d, _ = _pwm()
        desc = d.descriptor()
        assert desc["type"] == "pwm" and desc["lanes"] == ["request"]
        assert desc["value"] == "0.0-1.0"
        assert {c["name"] for c in desc["channels"]} == {"intake", "exhaust"}


class TestMinDuty:
    def _pwm_min(self, min_duty):
        cfg = EffectorConfig(id="fans", type="pwm", backend={"device": "d"},
                             channels=[EffectorChannel(name="a", index=0)],
                             params={"min_duty": min_duty})
        e = PwmEffector("fans", cfg)
        fake = FakeDevice()
        e.attach_devices({"d": fake})
        return e, fake

    def test_zero_level_is_fully_off(self):
        e, fake = self._pwm_min(0.3)
        e.handle_request({"levels": {"a": 0.0}})
        assert fake.calls[-1] == (CMD_SET_DUTY, [0, 0])

    def test_nonzero_maps_into_floor(self):
        e, fake = self._pwm_min(0.3)
        e.handle_request({"levels": {"a": 0.5}})           # (0.3 + 0.7*0.5)*255
        assert fake.calls[-1] == (CMD_SET_DUTY, [0, 166])

    def test_full_is_max(self):
        e, fake = self._pwm_min(0.3)
        e.handle_request({"levels": {"a": 1.0}})
        assert fake.calls[-1] == (CMD_SET_DUTY, [0, 255])

    def test_no_floor_by_default(self):
        e, fake = self._pwm_min(0.0)
        e.handle_request({"levels": {"a": 0.5}})
        assert fake.calls[-1] == (CMD_SET_DUTY, [0, 128])

    def test_descriptor_reports_min_duty(self):
        e, _ = self._pwm_min(0.3)
        assert e.descriptor()["min_duty"] == 0.3


class TestStreamLane:
    def test_stream_sink_accumulates(self):
        e = create_effector(EffectorConfig(id="spk", type="stream_sink"))
        e.feed(b"abcd")
        e.feed(b"xy")
        assert e.state() == {"bytes_received": 6, "last_chunk": 2}
        assert e.lanes == ("stream",)


def test_create_effector_unknown_type():
    with pytest.raises(ValueError):
        create_effector(EffectorConfig(id="x", type="bogus"))
