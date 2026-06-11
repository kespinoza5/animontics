"""Unit tests for the servo effector — angle map, clamps, both backends (no hardware)."""
from __future__ import annotations

from core.effector_base import create_effector
from core.mcu_link import CMD_SET_US
from core.models import EffectorChannel, EffectorConfig
from effectors.servo.effector import ServoEffector


class FakeDevice:
    def __init__(self):
        self.calls = []
    def send_command(self, cmd_id, args):
        self.calls.append((cmd_id, list(args)))
        return True


def _servo(params=None, backend=None):
    cfg = EffectorConfig(
        id="neck", type="servo",
        backend=backend or {"kind": "mcu", "device": "d"},
        params=params or {},
        channels=[EffectorChannel(name="yaw", index=0),
                  EffectorChannel(name="pitch", index=1)],
    )
    e = ServoEffector("neck", cfg)
    fake = FakeDevice()
    e.attach_devices({"d": fake})
    return e, fake


class TestAngleMap:
    def test_default_map_endpoints_and_centre(self):
        e, fake = _servo()
        e.handle_request({"angles": {"yaw": 0, "pitch": 180}})
        assert (CMD_SET_US, [0, 500]) in fake.calls
        assert (CMD_SET_US, [1, 2500]) in fake.calls
        e.handle_request({"angles": {"yaw": 90}})
        assert (CMD_SET_US, [0, 1500]) in fake.calls

    def test_soft_limits_clamp(self):
        e, fake = _servo(params={"deg_min": 30, "deg_max": 150})
        e.handle_request({"angles": {"yaw": 0}})        # below soft limit
        us = fake.calls[0][1][1]
        assert us == 500                                # clamped to deg_min end
        e.handle_request({"angles": {"yaw": 999}})
        assert fake.calls[1][1][1] == 2500

    def test_per_channel_override_and_trim(self):
        e, fake = _servo(params={
            "per_channel": {"yaw": {"trim_deg": 10}, "pitch": {"invert": True}},
        })
        e.handle_request({"angles": {"yaw": 80, "pitch": 0}})
        yaw_us = dict((args[0], args[1]) for _, args in fake.calls)[0]
        assert yaw_us == 1500                           # 80 + 10 trim = 90 deg
        pitch_us = dict((args[0], args[1]) for _, args in fake.calls)[1]
        assert pitch_us == 2500                         # inverted: 0 deg → max

    def test_raw_us_clamped(self):
        e, fake = _servo()
        e.handle_request({"us": {"yaw": 9999}})
        assert fake.calls[0] == (CMD_SET_US, [0, 2500])

    def test_state_and_results(self):
        e, _ = _servo()
        out = e.handle_request({"angles": {"yaw": 45}, "us": {"pitch": 1200}})
        assert out["set"] == {"yaw": "ok", "pitch": "ok"}
        assert e.state()["yaw"]["deg"] == 45
        assert e.state()["pitch"]["us"] == 1200

    def test_unknown_channel_and_empty(self):
        e, _ = _servo()
        assert e.handle_request({"angles": {"nope": 1}})["set"]["nope"] == "unknown channel"
        assert "error" in e.handle_request({})


class TestSbcPwmBackend:
    def test_sysfs_writes(self, tmp_path):
        chip = tmp_path / "pwmchip0"
        chip.mkdir()
        (chip / "export").write_text("")
        line = chip / "pwm0"
        line.mkdir()                                    # pretend export worked
        for f in ("period", "duty_cycle", "enable"):
            (line / f).write_text("")
        e, _ = _servo(backend={"kind": "sbc_pwm", "chip": 0, "root": str(tmp_path)})
        out = e.handle_request({"angles": {"yaw": 90}})
        assert out["set"]["yaw"] == "ok"
        assert (line / "period").read_text() == "20000000"      # 50 Hz in ns
        assert (line / "duty_cycle").read_text() == "1500000"   # 1500 µs in ns
        assert (line / "enable").read_text() == "1"
        e.stop()
        assert (line / "enable").read_text() == "0"

    def test_missing_chip_reports_link_down(self, tmp_path):
        e, _ = _servo(backend={"kind": "sbc_pwm", "chip": 3, "root": str(tmp_path)})
        assert e.handle_request({"angles": {"yaw": 90}})["set"]["yaw"] == "link down"


def test_registry():
    cfg = EffectorConfig(id="s", type="servo",
                         channels=[EffectorChannel(name="a", index=0)])
    assert isinstance(create_effector(cfg), ServoEffector)
