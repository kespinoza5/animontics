# gpio_out (arduino module)

Digital outputs: an optional non-blocking heartbeat blink (status LED) **and/or** a
commandable line driven from the inbound `CMD_SET_GPIO` lane (e.g. a relay IN).
**role:** actuator · **claims:** gpio pins · **accepts:** `set_gpio {channel,
level}` (CMD_SET_GPIO = 3) · **config:** `blink_ms` (0 = static / command-owned;
>0 = status-LED toggle).

- `gpio_out.h/.cpp` — `setup()` drives pins LOW; `tick(now)` toggles at `blink_ms`;
  `set_gpio(idx, on)` drives a pin from a command (the node already applied
  `active_low`).
- `decl/setup/loop.j2` — instance, `pinMode`, `tick(now)`; `cmd.j2` — the
  `CMD_SET_GPIO` case in the generated `onCommand()`.

A relay uses `blink_ms: 0` and is driven by the node's
[`power_rail`](../../../../effectors/power_rail) effector (`backend: {kind: mcu,
device, channel, active_low}`) → `core/gpio.McuOutputLine` → `CMD_SET_GPIO`. The
command `channel` is the firmware's running actuator offset (after any `pwm_out`
fans), so module order in the contract sets it.
