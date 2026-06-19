# mcu/arduino/ — AVR/Arduino firmware family

Source for forge's `target: mcu.arduino` — AVR (ATmega328P Nano/Uno) **and**
Renesas RA4M1 (Arduino UNO R4 core; e.g. the Waveshare RA4M1-Zero). Organized by
**runtime** (arduino-cli), not chip. `ArduinoBuilder`
(`tools/forge/builders/arduino.py`) renders these into a sketch and compiles it
with `arduino-cli` (WSL fallback).

```
arduino/
├── platform.yaml          family pins/tools + inline AVR board profiles (→ FQBN)
├── boards/<profile>.yaml  per-board pin tables, merged over platform.yaml (e.g. ra4m1_zero)
├── templates/main.ino.j2  the sketch skeleton: setup() inits modules, loop() ticks + flushes
└── modules/<name>/        manifest.yaml + <name>.h/.cpp + {decl,setup,read,send,loop,cmd}.j2
```

## Boards

`platform.yaml` defines the AVR profiles inline — `nano` (`arduino:avr:nano`),
`nano_old` (legacy bootloader), `uno`. Larger pin maps live in `boards/` and are
merged over the inline map: `ra4m1_zero` (`arduino:renesas_uno:minima`, the
Waveshare RA4M1-Zero). Pick one as `board:` in the contract. See
[boards/README.md](boards/README.md).

## Modules

| Module | Role | Claims | Provides / Accepts |
| --- | --- | --- | --- |
| `analog_in` | sensor | adc pins | one channel per pin (raw int16); RA4M1: optional `aref: external` (AREF=5 V) + `adc_bits` |
| `serial_sonar` | sensor | uart | MaxBotix `R<NNN>` off a hardware UART → 1 channel (inches) |
| `tach` | sensor | countio pins | one RPM channel per FG pin (pin-change ISR) |
| `pwm_out` | actuator | pwm pins | accepts `set_duty {channel, duty}` (`freq_hz` not yet honored — bench TODO) |
| `gpio_out` | actuator | gpio pins | heartbeat blink (`blink_ms`) and/or `set_gpio` (CMD_SET_GPIO, e.g. a relay) |
| `transport_serial` | transport | uart | frames the sample vector + inbound command poll (protocol v1) |

The `cmd.j2` fragment is a case in the generated `onCommand()` (inbound
command lane, fed by `transport_serial.poll`) — `pwm_out` (`CMD_SET_DUTY`) and
`gpio_out` (`CMD_SET_GPIO`) use it.

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
