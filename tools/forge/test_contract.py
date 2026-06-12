"""Unit tests for contract validation + channel assignment (no disk, no hardware)."""
from __future__ import annotations

from tools.forge.contract import (
    McuChannel,
    McuModule,
    McuTarget,
    assign_channels,
    provided_sources,
    validate,
)

# Synthetic platform + manifests standing in for mcu/arduino/ (built in Phase 2).
PLATFORM = {
    "boards": {"nano": {"fqbn": "arduino:avr:nano"}},
    "pins": {
        "adc": ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7"],
        "pwm": ["D3", "D5", "D6", "D9", "D10", "D11"],
        "gpio": ["D2", "D4", "D7", "D8", "D12", "D13"],
        "uart": ["D0", "D1"],
    },
}
MANIFESTS = {
    "analog_in": {"module": "analog_in", "platforms": ["arduino"], "role": "sensor",
                  "claims": {"pins": "adc"}, "provides": {"channels": "per_pin"}},
    "pwm_out": {"module": "pwm_out", "platforms": ["arduino"], "role": "actuator",
                "claims": {"pins": "pwm"}},
    "gpio_out": {"module": "gpio_out", "platforms": ["arduino"], "role": "actuator",
                 "claims": {"pins": "gpio"}},
    "transport_serial": {"module": "transport_serial", "platforms": ["arduino"],
                         "role": "transport", "claims": {"pins": "uart"}},
}


def _target(**kw) -> McuTarget:
    base = dict(id="t", target="mcu.arduino", board="nano")
    base.update(kw)
    return McuTarget.model_validate(base)


class TestChannelAssignment:
    def test_per_pin_indices_follow_module_order(self):
        target = _target(modules=[
            {"module": "analog_in", "pins": ["A7", "A6", "A0"]},
            {"module": "transport_serial"},
        ])
        chans = assign_channels(target, MANIFESTS)
        assert [(c.index, c.source) for c in chans] == [
            (0, "analog_in.A7"), (1, "analog_in.A6"), (2, "analog_in.A0"),
        ]

    def test_preserves_user_signal_and_calibration(self):
        target = _target(
            modules=[{"module": "analog_in", "pins": ["A7", "A6"]},
                     {"module": "transport_serial"}],
            channels=[McuChannel(index=0, source="analog_in.A7", signal="mq135",
                                 calibration={"type": "mq", "r0": 76.0})],
        )
        chans = assign_channels(target, MANIFESTS)
        assert chans[0].signal == "mq135"
        assert chans[0].calibration["r0"] == 76.0
        assert chans[1].signal == "analog_in.A6"          # default for the new one

    def test_actuators_and_transport_provide_no_channels(self):
        target = _target(modules=[
            {"module": "pwm_out", "pins": ["D3", "D5"]},
            {"module": "transport_serial"},
        ])
        assert provided_sources(target, MANIFESTS) == []


class TestValidate:
    def test_clean_contract(self):
        target = _target(modules=[
            {"module": "analog_in", "pins": ["A0", "A1"]},
            {"module": "pwm_out", "pins": ["D3"]},
            {"module": "transport_serial"},
        ])
        assert validate(target, PLATFORM, MANIFESTS) == []

    def test_unknown_module(self):
        target = _target(modules=[{"module": "lasers"}, {"module": "transport_serial"}])
        assert any("unknown module 'lasers'" in e for e in validate(target, PLATFORM, MANIFESTS))

    def test_pin_wrong_kind(self):
        target = _target(modules=[
            {"module": "analog_in", "pins": ["D3"]},          # D3 is pwm, not adc
            {"module": "transport_serial"},
        ])
        assert any("not a valid adc pin" in e for e in validate(target, PLATFORM, MANIFESTS))

    def test_pin_conflict_between_modules(self):
        target = _target(modules=[
            {"module": "pwm_out", "pins": ["D3"]},
            {"module": "gpio_out", "pins": ["D3"]},           # same physical pin
            {"module": "transport_serial"},
        ])
        assert any("claimed by both" in e for e in validate(target, PLATFORM, MANIFESTS))

    def test_requires_exactly_one_transport(self):
        none = _target(modules=[{"module": "analog_in", "pins": ["A0"]}])
        assert any("exactly one transport" in e for e in validate(none, PLATFORM, MANIFESTS))
        two = _target(modules=[{"module": "transport_serial"}, {"module": "transport_serial"}])
        assert any("exactly one transport" in e for e in validate(two, PLATFORM, MANIFESTS))

    def test_unknown_board(self):
        target = _target(board="uno", modules=[{"module": "transport_serial"}])
        assert any("board 'uno'" in e for e in validate(target, PLATFORM, MANIFESTS))

    def test_channel_count_mismatch(self):
        target = _target(
            modules=[{"module": "analog_in", "pins": ["A0", "A1"]},
                     {"module": "transport_serial"}],
            channels=[McuChannel(index=0, source="analog_in.A0", signal="x")],  # only 1 of 2
        )
        assert any("channels: contract lists 1" in e for e in validate(target, PLATFORM, MANIFESTS))
