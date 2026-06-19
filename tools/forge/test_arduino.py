"""Composer tests for the Arduino builder — pure rendering, no toolchain/hardware."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.forge.builder import BuildContext
from tools.forge.builders.arduino import ArduinoBuilder, _pin, _to_wsl_path
from tools.forge.contract import McuTarget

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _ctx(tmp_path: Path) -> BuildContext:
    target = McuTarget.model_validate({
        "id": "t", "target": "mcu.arduino", "board": "nano",
        "transport": {"type": "serial", "baud": 115200},
        "modules": [
            {"module": "analog_in", "pins": ["A7", "A0"], "sample_hz": 4},
            {"module": "pwm_out", "pins": ["D3"]},
            {"module": "gpio_out", "pins": ["D13"], "blink_ms": 250},
            {"module": "transport_serial"},
        ],
    })
    return BuildContext(contract=target, project_root=PROJECT_ROOT, out_dir=tmp_path / "t")


class TestCompose:
    def test_generates_valid_looking_sketch(self, tmp_path):
        sketch = ArduinoBuilder().compose(_ctx(tmp_path))
        ino = (sketch / "t.ino").read_text(encoding="utf-8")

        # one #include per used module header, each on its own line
        assert ino.count('#include "') == 4
        for header in ("analog_in.h", "pwm_out.h", "gpio_out.h", "transport_serial.h"):
            assert f'#include "{header}"\n' in ino

        # direct, concrete instances (no registry / vtables)
        assert "AnalogIn analog_in0(analog_in0_pins, 2, AnalogIn::AREF_DEFAULT, 0);" in ino
        assert "PwmOut pwm_out0(pwm_out0_pins, 1);" in ino
        assert "GpioOut gpio_out0(gpio_out0_pins, 1, 250UL);" in ino
        assert "TransportSerial transport_serial0;" in ino

        # pin translation: analog keeps An, digital strips the D
        assert "{ A7, A0 }" in ino
        assert "{ 3 }" in ino and "{ 13 }" in ino

        # composed loop wiring + globals
        assert "CHANNEL_COUNT = 2;" in ino           # only analog_in provides channels
        assert "SAMPLE_PERIOD_MS = 250;" in ino       # 4 Hz → 250 ms
        assert "analog_in0.read(g_frame + 0);" in ino
        assert "transport_serial0.send(g_frame, CHANNEL_COUNT, g_seq);" in ino
        assert "gpio_out0.tick(now);" in ino          # actuator loop fragment

    def test_copies_module_sources(self, tmp_path):
        sketch = ArduinoBuilder().compose(_ctx(tmp_path))
        for src in ("analog_in.h", "analog_in.cpp", "pwm_out.cpp",
                    "gpio_out.cpp", "transport_serial.cpp"):
            assert (sketch / src).exists()

    def test_channel_offsets_accumulate(self, tmp_path):
        target = McuTarget.model_validate({
            "id": "t", "target": "mcu.arduino", "board": "nano",
            "modules": [
                {"module": "analog_in", "pins": ["A0", "A1"]},
                {"module": "analog_in", "pins": ["A2"]},
                {"module": "transport_serial"},
            ],
        })
        ctx = BuildContext(contract=target, project_root=PROJECT_ROOT, out_dir=tmp_path / "t")
        ino = (ArduinoBuilder().compose(ctx) / "t.ino").read_text(encoding="utf-8")
        assert "analog_in0.read(g_frame + 0);" in ino
        assert "analog_in1.read(g_frame + 2);" in ino   # second module starts after the first two
        assert "CHANNEL_COUNT = 3;" in ino


def test_pin_translation():
    assert _pin("D13") == "13"
    assert _pin("D3") == "3"
    assert _pin("A0") == "A0"
    assert _pin("A7") == "A7"


@pytest.mark.skipif(os.name != "nt", reason="WSL path mapping is a Windows-only concern")
def test_wsl_path_mapping():
    assert _to_wsl_path(Path(r"C:\Users\x\firmware")) == "/mnt/c/Users/x/firmware"
