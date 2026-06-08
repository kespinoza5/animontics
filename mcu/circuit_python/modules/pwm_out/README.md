# pwm_out (circuit_python module)

Hardware PWM outputs via CircuitPython `pwmio.PWMOut` — e.g. the 25 kHz PWM input
of a 4-pin fan. **role:** actuator · **accepts:** `set_duty {channel, duty}`
(duty 0–255 → `pwmio` 0–65535).

The RP2040/RP2350 sets a clean per-channel frequency in one line, so unlike the
AVR family there's no timer juggling. `pins` (CircuitPython board attribute names
like `D1`, `GP2`) and `freq_hz` come from the contract; the composer renders them
into `code.py`, which sets up the `pwmio` channels and drives them from inbound
`set_duty` command frames decoded off USB serial.

Pick pins on **distinct PWM slices** — `pwmio` raises if two share a slice/channel.
The fan's PWM line is a logic input (drive it directly / through a level shifter);
the fan's V+/GND are powered separately (not from a GPIO).
