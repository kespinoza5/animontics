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
    # kind-tagged frame sources: (0, addr, channel, gain) for ADS
    assert "(0, 72, 0, 1)," in code and "(0, 72, 1, 1)," in code and "(0, 73, 0, 2)," in code
    assert "time.sleep(0.25)" in code            # 4 Hz sample loop
    assert 'b"AM"' in code                       # mcu_link framing mirrored


def test_validate_requires_a_sensor_or_actuator(tmp_path):
    target = McuTarget.model_validate({
        "id": "p", "target": "mcu.circuit_python", "board": "xiao_samd21",
        "modules": [{"module": "transport_serial"}],   # neither ads1115 nor pwm_out
    })
    ctx = BuildContext(contract=target, project_root=PROJECT_ROOT, out_dir=tmp_path / "p")
    assert CircuitPythonBuilder().validate(ctx)        # flags the empty board


def _pwm_ctx(tmp_path) -> BuildContext:
    target = McuTarget.model_validate({
        "id": "fans", "target": "mcu.circuit_python", "board": "xiao_rp2040",
        "modules": [
            {"module": "pwm_out", "pins": ["D1", "D2", "D3"], "freq_hz": 25000},
            {"module": "transport_serial"},
        ],
    })
    return BuildContext(contract=target, project_root=PROJECT_ROOT, out_dir=tmp_path / "fans")


def test_compose_pwm_only_runtime(tmp_path):
    out = CircuitPythonBuilder().compose(_pwm_ctx(tmp_path))
    code = (out / "code.py").read_text(encoding="utf-8")
    assert "import pwmio" in code
    assert "PWM_FREQ = 25000" in code
    assert 'pwmio.PWMOut(getattr(board, "D1"), frequency=PWM_FREQ' in code
    assert "def poll_commands()" in code           # inbound command lane present
    assert "if cmd == 1 and nargs >= 2:" in code    # CMD_SET_DUTY dispatch
    assert "def read_all()" not in code             # no sensor section
    assert "ADS.ADS1115(" not in code               # no ADS instantiation


def test_compose_sensor_plus_pwm(tmp_path):
    target = McuTarget.model_validate({
        "id": "both", "target": "mcu.circuit_python", "board": "xiao_rp2040",
        "modules": [
            {"module": "ads1115", "chips": [{"addr": 0x48, "gain": 1, "channels": [0]}]},
            {"module": "pwm_out", "pins": ["D1"]},
            {"module": "transport_serial"},
        ],
    })
    ctx = BuildContext(contract=target, project_root=PROJECT_ROOT, out_dir=tmp_path / "both")
    code = (CircuitPythonBuilder().compose(ctx) / "code.py").read_text(encoding="utf-8")
    assert "def read_all()" in code and "def poll_commands()" in code   # both lanes
    assert "send(read_all(), seq)" in code and "poll_commands()" in code


def _scan_ctx(tmp_path, mcu_id: str, modules: list[dict]) -> BuildContext:
    target = McuTarget.model_validate({
        "id": mcu_id, "target": "mcu.circuit_python", "board": "xiao_samd21",
        "modules": modules + [{"module": "transport_serial"}],
    })
    return BuildContext(contract=target, project_root=PROJECT_ROOT, out_dir=tmp_path / mcu_id)


_CONDUCTOR = {
    "module": "matrix_scan", "pins": ["D5", "D6", "D9", "D4", "D13"],
    "rows": 16, "dac_pin": "A0", "ack_pins": ["A1", "A2", "A3"],
    "settle_ms": 2, "ack_timeout_ms": 50, "sample_hz": 32,
}
_FOLLOWER = {
    "module": "scan_follower", "rows": 16,
    "watch_pin": "A1", "ack_pin": "A0", "watch_timeout_ms": 250,
}


def test_compose_matrix_scan_conductor(tmp_path):
    ctx = _scan_ctx(tmp_path, "cond", [
        _CONDUCTOR,
        {"module": "analog_in", "pins": ["A4", "A5"]},
    ])
    code = (CircuitPythonBuilder().compose(ctx) / "code.py").read_text(encoding="utf-8")
    assert "SCAN_ROWS = 16" in code and "def _advance_row():" in code
    assert "(3, 0, 0, 0)," in code                       # row tag frame source
    assert code.index("(3, 0, 0, 0),") < code.index("(2, 0, 0, 0),")  # row tag is channel 0
    assert '_dac = analogio.AnalogOut(getattr(board, "A0"))' in code
    assert "['D5', 'D6', 'D9']" in code and "['D4', 'D13']" in code   # sel + inh pins
    assert "_advance_row()" in code.split("while True:")[1]           # runs every tick
    assert "def _await_row():" not in code                            # not a follower
    compile(code, "cond.py", "exec")                                  # valid python


def test_compose_scan_follower(tmp_path):
    ctx = _scan_ctx(tmp_path, "fol", [
        _FOLLOWER,
        {"module": "analog_in", "pins": ["A2", "A3"], "sample_hz": 4},
    ])
    code = (CircuitPythonBuilder().compose(ctx) / "code.py").read_text(encoding="utf-8")
    assert "def _await_row():" in code and "def _ack_row():" in code
    assert "_row = -1" in code                            # timeout sentinel
    loop = code.split("while True:")[1]
    # spec order: await -> sample -> ack -> send
    assert loop.index("_await_row()") < loop.index("read_all()") \
        < loop.index("_ack_row()") < loop.index("send(samples, seq)")
    assert "time.sleep(0.005)" in loop                    # paced by the conductor
    assert "def _advance_row():" not in code              # not a conductor
    compile(code, "fol.py", "exec")


def test_compose_servo_out(tmp_path):
    ctx = _scan_ctx(tmp_path, "neck", [
        {"module": "servo_out", "pins": ["A4", "A5", "A6"], "freq_hz": 50,
         "min_us": 500, "max_us": 2500},
        {"module": "analog_in", "pins": ["A1", "A2", "A3"], "sample_hz": 50},
    ])
    code = (CircuitPythonBuilder().compose(ctx) / "code.py").read_text(encoding="utf-8")
    assert "SERVO_FREQ = 50" in code and "SERVO_MIN_US = 500" in code
    assert 'pwmio.PWMOut(getattr(board, "A4"), frequency=SERVO_FREQ, duty_cycle=0)' in code
    assert "if cmd == 2 and nargs >= 2:" in code          # CMD_SET_US dispatch
    assert "def _set_us(ch, us):" in code
    assert ".value >> 1" in code                          # native ADC int16-safe
    assert "def poll_commands()" in code and "def read_all()" in code
    compile(code, "neck.py", "exec")


def test_validate_scan_modules(tmp_path):
    builder = CircuitPythonBuilder()
    # conductor + follower on one board is contradictory
    both = _scan_ctx(tmp_path, "x", [dict(_CONDUCTOR), dict(_FOLLOWER)])
    assert any("mutually exclusive" in i for i in builder.validate(both))
    # rows must fit 8 x inhibit pins
    too_many_rows = dict(_CONDUCTOR, pins=["D5", "D6", "D9", "D4"], rows=16)
    ctx = _scan_ctx(tmp_path, "y", [too_many_rows])
    assert any("rows > 8 x" in i for i in builder.validate(ctx))
    # follower needs its handshake pins
    bare = {"module": "scan_follower", "rows": 16}
    ctx = _scan_ctx(tmp_path, "z", [bare])
    assert any("watch_pin and ack_pin" in i for i in builder.validate(ctx))


def test_compose_pwm_plus_tach(tmp_path):
    # the LXiao shape: drive fans + read their RPM on one bidirectional board
    target = McuTarget.model_validate({
        "id": "lx", "target": "mcu.circuit_python", "board": "xiao_rp2040",
        "modules": [
            {"module": "pwm_out", "pins": ["D1", "D2"], "freq_hz": 25000},
            {"module": "tach", "pins": ["D7", "D8"], "pulses_per_rev": 2, "sample_hz": 4},
            {"module": "transport_serial"},
        ],
    })
    ctx = BuildContext(contract=target, project_root=PROJECT_ROOT, out_dir=tmp_path / "lx")
    code = (CircuitPythonBuilder().compose(ctx) / "code.py").read_text(encoding="utf-8")
    assert "import countio" in code
    assert 'countio.Counter(getattr(board, "D7"))' in code
    assert "(1, 0, 0, 0)," in code and "(1, 1, 0, 0)," in code   # two tach frame sources
    assert "def _read_rpm(i):" in code
    assert "def read_all()" in code and "def poll_commands()" in code  # both lanes
    assert "ADS.ADS1115(" not in code                                  # no ADS on this board
