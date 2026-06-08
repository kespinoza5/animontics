# mcu/circuit_python/modules/ — CircuitPython modules

Modules for the CircuitPython family. Unlike the AVR modules these carry **no
compiled sources** — they parameterize the generic runtime
(`templates/code.py.j2`) that `CircuitPythonBuilder` renders into
`firmware/<id>/code.py`. Each is a directory with a `manifest.yaml`.

| Module | Role | Notes |
|--------|------|-------|
| `ads1115` | sensor | I2C ADS1115 chips (addr/gain/channels); one channel per (chip, channel) |
| `tach` | sensor | fan FG pulse counting (`countio`) → RPM; one channel per FG pin |
| `pwm_out` | actuator | `pwmio` PWM outputs (e.g. 25 kHz fan PWM); driven by `set_duty` commands |
| `transport_serial` | transport | marks the USB-serial uplink (framing lives in `code.py`) |

The runtime composes an ordered, kind-tagged `FRAME_SOURCES` list (ADS reads +
tach RPM) for the afferent lane and a PWM command handler for the efferent lane,
both conditional — so a board can be sensor-only, actuator-only, or **both** (the
LXiao drives fans *and* reads their RPM).

See [CONTRIBUTING.md](../../../CONTRIBUTING.md#adding-an-mcu-target-firmware-module).
