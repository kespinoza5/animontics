# mcu/circuit_python/ — CircuitPython firmware family

Source for forge's `target: mcu.circuit_python` — any CircuitPython-capable board
(XIAO SAMD21, RP2040, …). Unlike the AVR family there is **no compile step**:
`CircuitPythonBuilder` renders one generic runtime with the instance's ADS1115
chip list baked in, into `firmware/<id>/code.py`, and "deploys" by copying it to
the board's `CIRCUITPY` drive. Families are organized by runtime, not chip — the
board is just a profile in `platform.yaml`.

The runtime is bidirectional: it streams ADS1115 channels (afferent) **and/or**
drives PWM outputs from inbound commands (efferent) — whichever modules the
contract composes.

```
circuit_python/
├── platform.yaml          board profiles (xiao_samd21/rp2040/rp2350, pico), runtime, deploy: copy
├── templates/code.py.j2   generic runtime: ADS1115 stream + PWM command lane (conditional)
└── modules/
    ├── ads1115/           sensor — declares chips (addr/gain/channels), provides channels
    ├── tach/              sensor — countio edge-counting for fan FG (RPM); one channel per pin
    ├── pwm_out/           actuator — pwmio PWM (e.g. 25 kHz fan PWM), set_duty commands
    └── transport_serial/  marks the uplink transport (framing is in code.py)
```

## How a build works

```bash
python -m tools.forge.forge build press0     # → firmware/press0/code.py
```

The contract (`config/mcus/press0.yaml`) lists the ADS1115 chips; forge flattens
them to an ordered `(addr, channel, gain)` list and renders `code.py`, which scans
them each tick and writes **`core/mcu_link.py`** frames over USB serial. The node's
`McuSerialDevice` decodes those frames identically to an AVR board — so the same
`pressure_array` sensor works regardless of which MCU produced the stream.

The runtime mirrors the `core/mcu_link.py` frame layout (magic `AM`, version, seq,
`int16[]`, checksum). Change one ⇒ bump `PROTOCOL_VERSION` in both.

Adding a board profile or module: see
[CONTRIBUTING.md](../../CONTRIBUTING.md#adding-an-mcu-target-firmware-module) and
[docs/forge.md](../../docs/forge.md).
