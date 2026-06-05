# mcu/arduino/ — AVR/Arduino firmware family

Source for forge's first target, `target: mcu.arduino` (ATmega328P — Nano/Uno).
`ArduinoBuilder` (`tools/forge/builders/arduino.py`) renders these into a sketch
and compiles it with `arduino-cli`.

```
arduino/
├── platform.yaml          board profiles (→ FQBN), valid pins per kind, compile/flash tools
├── templates/main.ino.j2  the sketch skeleton: setup() inits modules, loop() ticks + flushes
└── modules/<name>/        manifest.yaml + <name>.h/.cpp + {decl,setup,read,send,loop}.j2
```

## Boards

`platform.yaml` defines `nano` (`arduino:avr:nano`), `nano_old` (legacy
bootloader), and `uno`. Pick one as `board:` in the contract.

## Modules

| Module | Role | Claims | Provides / Accepts |
| --- | --- | --- | --- |
| `analog_in` | sensor | adc pins | one channel per pin (raw int16) |
| `pwm_out` | actuator | pwm pins | accepts `set_duty {channel, duty}` |
| `gpio_out` | actuator | gpio pins | optional heartbeat blink (`blink_ms`) |
| `transport_serial` | transport | uart (D0/D1) | frames the sample vector (protocol v1) |

A module is a small hand-written C++ class (`setup()` + its work method) plus
jinja fragments the composer drops into the sketch: `decl.j2` (global instance),
`setup.j2` (init), and one of `read.j2` (sensor → frame), `send.j2` (transport),
or `loop.j2` (actuator tick). Fragments render with a uniform context (`inst`,
`pins`, `params`, `offset`, `count`, `channel_count`, `baud`).

## Toolchain

`forge build` calls `arduino-cli`, falling back to running it inside **WSL** with
path translation when it is not on `PATH`. One-time install:

```bash
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
  | BINDIR="$HOME/.local/bin" sh
arduino-cli core update-index && arduino-cli core install arduino:avr
```

The frame layout is authoritative in [`core/mcu_link.py`](../../core/mcu_link.py);
`transport_serial` encodes the identical bytes. Change one ⇒ bump `VERSION` in both.

See [CONTRIBUTING.md](../../CONTRIBUTING.md#adding-an-mcu-target-firmware-module)
to add a module.
