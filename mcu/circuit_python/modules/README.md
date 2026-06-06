# mcu/circuit_python/modules/ — CircuitPython modules

Modules for the CircuitPython family. Unlike the AVR modules these carry **no
compiled sources** — they parameterize the generic runtime
(`templates/code.py.j2`) that `CircuitPythonBuilder` renders into
`firmware/<id>/code.py`. Each is a directory with a `manifest.yaml`.

| Module | Role | Notes |
|--------|------|-------|
| `ads1115` | sensor | declares the I2C ADS1115 chips (addr/gain/channels); provides one channel per (chip, channel) |
| `transport_serial` | transport | marks the USB-serial uplink (framing lives in `code.py`) |

See [CONTRIBUTING.md](../../../CONTRIBUTING.md#adding-an-mcu-target-firmware-module).
