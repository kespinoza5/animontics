# mcu/circuit_python/modules/ — CircuitPython modules

Modules for the CircuitPython family. Unlike the AVR modules these carry **no
compiled sources** — they parameterize the generic runtime
(`templates/code.py.j2`) that `CircuitPythonBuilder` renders into
`firmware/<id>/code.py`. Each is a directory with a `manifest.yaml`.

| Module | Role | Notes |
|--------|------|-------|
| `ads1115` | sensor | I2C ADS1115 chips (addr/gain/channels); one channel per (chip, channel) |
| `analog_in` | sensor | the board's own ADC pins (`analogio`); one channel per pin (`value >> 1` → int16) |
| `tach` | sensor | fan FG pulse counting (`countio`) → RPM; one channel per FG pin |
| `matrix_scan` | sensor | scanned-matrix **conductor**: CD4051 row energization + DAC sync broadcast; provides the row-tag channel |
| `scan_follower` | sensor | scanned-matrix **follower**: watch/sample/ack on the DAC handshake; provides the row-tag channel (-1 on timeout) |
| `pwm_out` | actuator | `pwmio` PWM outputs (e.g. 25 kHz fan PWM); driven by `set_duty` commands |
| `servo_out` | actuator | 50 Hz servo pulses; driven by `set_us` commands (µs, safety-clamped) |
| `transport_serial` | transport | marks the USB-serial uplink (framing lives in `code.py`) |

The runtime composes an ordered, kind-tagged `FRAME_SOURCES` list (ADS reads,
native ADC, tach RPM, scan row tags) for the afferent lane and a command handler
(PWM duty + servo µs) for the efferent lane, both conditional — so a board can be
sensor-only, actuator-only, or **both** (the LXiao drives fans *and* reads their
RPM; the cervical board drives servos *and* reads their pots). The matrix-scan
pair coordinates multiple MCUs into one scanned organ — the handshake spec lives
in [matrix_scan/README.md](matrix_scan/README.md).

See [CONTRIBUTING.md](../../../CONTRIBUTING.md#adding-an-mcu-target-firmware-module).
