# mcu/arduino/modules/ — composable AVR firmware modules

Reusable building blocks `forge` composes into an Arduino sketch. Each module is a
directory with:

- `manifest.yaml` — platforms, role (`sensor`/`actuator`/`transport`), pin claims,
  channels it provides / commands it accepts, config defaults, C++ sources.
- a lean C++ library (`<name>.h`/`.cpp`) — hardware I/O only, no framing/meaning.
- jinja fragments the composer drops into `templates/main.ino.j2`:
  `decl.j2` (global instance), `setup.j2` (init), and one of `read.j2` (sensor →
  frame), `send.j2` (transport), `loop.j2` (actuator tick), `cmd.j2` (command case).

| Module | Role | Claims | Notes |
|--------|------|--------|-------|
| `analog_in` | sensor | adc | one frame channel per pin |
| `pwm_out` | actuator | pwm | `set_duty` command target (fans, etc.) |
| `gpio_out` | actuator | gpio | digital out + optional heartbeat blink |
| `transport_serial` | transport | uart | protocol-v1 framing + inbound command poll |

Adding a module: see
[CONTRIBUTING.md](../../../CONTRIBUTING.md#adding-an-mcu-target-firmware-module).
