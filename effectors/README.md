# effectors

Effector plugin packages — the efferent dual of `sensors/`. Each subdirectory is
a self-contained package for one output **type** (motion, light, sound). The base
class + registry live in [`core/effector_base.py`](../core/effector_base.py); this
tree holds the concrete types, auto-discovered exactly like sensors.

## Plugin system

`effectors/__init__.py` uses `pkgutil.iter_modules` to import every package on
disk, firing each `@register_effector("type")`. `node/app.py` imports `effectors`
once; instances are created from the board config's `effectors:` list and bound to
their backend device.

## Available types

| Package | Type | Lane(s) | Drives |
|---------|------|---------|--------|
| [`pwm/`](pwm/README.md) | `pwm` | request | named PWM channels (LED, motor speed) |
| [`fan_array/`](fan_array/README.md) | `fan_array` | request | named fans (PWM + per-fan `min_duty`) |
| [`servo/`](servo/README.md) | `servo` | request | hobby servos by angle/µs — `mcu` (CMD_SET_US) or `sbc_pwm` (/sys/class/pwm) backend |
| [`power_rail/`](power_rail/README.md) | `power_rail` | request | a switchable power rail; members report *gated*, not failed; publishes `power.<id>` |
| [`speaker/`](speaker/README.md) | `speaker` | request + stream | ALSA playback (raw S16_LE) + the amp's SD-pin gate |
| [`stream_sink/`](stream_sink/README.md) | `stream_sink` | stream | reference continuous-flow sink |

## Adding an effector

Subclass `EffectorBase`, decorate `@register_effector("type")`, set `lanes`, and
implement the lane handler(s) your type uses: `handle_request(payload)` (request)
and/or `feed(chunk)` (stream). Drive values are type-defined and normalized; the
node scales to the device's raw command. See
[CONTRIBUTING.md](../CONTRIBUTING.md#adding-a-device-effector-or-policy).
