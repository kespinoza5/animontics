# gpio_out (circuit_python module)

Digital output pins via `digitalio`, driven by inbound `set_gpio` commands
(`CMD_SET_GPIO = 3` in `core/mcu_link.py`: `[channel, 0|1]`, channel = the
pin's position in the contract's pin order). **role:** actuator.

All pins initialize to `initial` (default 0 — safe-off) at boot and stay there
until commanded, so a resetting MCU never glitches a power rail on.

Node-side counterpart: `core/gpio.py`'s **`mcu` backend** — any `OutputLine`
consumer (the `power_rail` effector, a modem power pin) can name
`{backend: mcu, device: <id>, channel: N}` and drive one of these pins through
the device's command sink. This is the seam the **brainstem** uses: the
Waveshare RP2040 power controllers expose every SBC/MCU power/reset line as
`gpio_out` channels. (Autonomous watchdog behaviour for those controllers is a
recorded follow-up — today they are command-driven only.)

The AVR family has a `gpio_out` of the same name (used for the heartbeat LED);
this is its CircuitPython twin with a command lane.
