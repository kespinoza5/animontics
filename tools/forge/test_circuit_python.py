"""Composer tests for the CircuitPython builder — pure rendering, no hardware."""
from __future__ import annotations

from pathlib import Path

from tools.forge.builder import BuildContext
from tools.forge.builders.circuit_python import CircuitPythonBuilder
from tools.forge.contract import McuTarget

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _ctx(tmp_path: Path) -> BuildContext:
    target = McuTarget.model_validate({
        "id": "p", "target": "mcu.circuit_python", "board": "xiao_samd21",
        "transport": {"type": "serial", "baud": 115200},
        "modules": [
            {"module": "ads1115", "sample_hz": 4, "chips": [
                {"addr": 0x48, "gain": 1, "channels": [0, 1]},
                {"addr": 0x49, "gain": 2, "channels": [0]},
            ]},
            {"module": "transport_serial"},
        ],
    })
    return BuildContext(contract=target, project_root=PROJECT_ROOT, out_dir=tmp_path / "p")


def test_compose_renders_runtime(tmp_path):
    out = CircuitPythonBuilder().compose(_ctx(tmp_path))
    code = (out / "code.py").read_text(encoding="utf-8")
    # chips instantiated by address
    assert "ADS.ADS1115(_i2c, address=72)" in code
    assert "ADS.ADS1115(_i2c, address=73)" in code
    # ordered (addr, channel, gain) wire list
    assert "(72, 0, 1)," in code and "(72, 1, 1)," in code and "(73, 0, 2)," in code
    assert "PERIOD_S = 0.25" in code            # 4 Hz
    assert 'b"AM"' in code                       # mcu_link framing mirrored


def test_validate_requires_ads1115(tmp_path):
    target = McuTarget.model_validate({
        "id": "p", "target": "mcu.circuit_python", "board": "xiao_samd21",
        "modules": [{"module": "transport_serial"}],
    })
    ctx = BuildContext(contract=target, project_root=PROJECT_ROOT, out_dir=tmp_path / "p")
    assert any("ads1115" in i for i in CircuitPythonBuilder().validate(ctx))
