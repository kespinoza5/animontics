"""Unit tests for the power_rail effector — switching, gating, backends (no hardware)."""
from __future__ import annotations

from core.effector_base import create_effector
from core.mcu_link import CMD_SET_GPIO
from core.models import EffectorChannel, EffectorConfig
from core.relay import Relay
from effectors.power_rail.effector import PowerRail


class FakeDevice:
    def __init__(self):
        self.calls = []
    def send_command(self, cmd_id, args):
        self.calls.append((cmd_id, list(args)))
        return True


def _rail(params=None, backend=None, devices=None):
    cfg = EffectorConfig(
        id="servo_rail", type="power_rail",
        backend=backend or {"kind": "mcu", "device": "brainstem", "channel": 2},
        params=params or {"members": ["samd21_cervical"]},
        channels=[EffectorChannel(name="main", index=0)],
    )
    e = PowerRail("servo_rail", cfg)
    devs = devices if devices is not None else {"brainstem": FakeDevice()}
    e.attach_devices(devs)
    return e, devs


class TestSwitching:
    def test_initial_on_by_default(self):
        e, devs = _rail()
        e.start()
        assert e.is_on() is True
        assert devs["brainstem"].calls == [(CMD_SET_GPIO, [2, 1])]

    def test_initial_off(self):
        e, devs = _rail(params={"initial": "off"})
        e.start()
        assert e.is_on() is False
        assert devs["brainstem"].calls == [(CMD_SET_GPIO, [2, 0])]

    def test_on_payload(self):
        e, devs = _rail()
        assert e.handle_request({"on": False}) == {"set": {"on": False}}
        assert devs["brainstem"].calls[-1] == (CMD_SET_GPIO, [2, 0])

    def test_policy_levels_lane(self):
        e, devs = _rail()
        e.handle_request({"levels": {"main": 0.0}})
        assert e.is_on() is False
        e.handle_request({"levels": {"main": 1.0}})
        assert e.is_on() is True

    def test_bad_payload(self):
        e, _ = _rail()
        assert "error" in e.handle_request({})


class TestGating:
    def test_members_gated_only_while_off(self):
        e, _ = _rail(params={"members": ["a", "b"]})
        assert e.gated_devices() == set()          # unknown state: nothing gated
        e.set_on(True)
        assert e.gated_devices() == set()
        e.set_on(False)
        assert e.gated_devices() == {"a", "b"}

    def test_relay_signal_published(self):
        e, _ = _rail()
        relay = Relay()
        e.attach_relay(relay)
        e.set_on(False)
        assert relay.latest("power.servo_rail") == 0
        e.set_on(True)
        assert relay.latest("power.servo_rail") == 1

    def test_descriptor_lists_members(self):
        e, _ = _rail(params={"members": ["x"]})
        d = e.descriptor()
        assert d["value"] == "on/off" and d["members"] == ["x"]


def test_gpio_backend_degrades_to_null_line():
    # libgpiod absent on the dev machine → NullOutputLine, never a crash
    e, _ = _rail(backend={"kind": "gpio",
                          "line": {"backend": "libgpiod", "chip": "gpiochip0",
                                   "line": 17, "active_low": True}},
                 devices={})
    e.start()                                      # logs, no raise
    assert e.is_on() is True                       # state tracked even with no pin


def test_registry():
    cfg = EffectorConfig(id="r", type="power_rail",
                         channels=[EffectorChannel(name="main", index=0)])
    assert isinstance(create_effector(cfg), PowerRail)
