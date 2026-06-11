# servo — hobby-servo position effector

Positions hobby servos by **angle** (or raw **µs** pulse width) over the request
lane: `POST /effectors/<id>` with `{"angles": {"yaw": 90}}` and/or
`{"us": {"yaw": 1500}}`. Channel keys are names or indices.

## Backends

| `backend` | Drives |
|-----------|--------|
| `{kind: mcu, device: <id>}` | `CMD_SET_US` command frames to an MCU running the `servo_out` firmware module (e.g. the cervical QtPy SAMD21 driving the DS3218 neck) |
| `{kind: sbc_pwm, chip: N}` | Linux hardware PWM via `/sys/class/pwm/pwmchipN` — channel `index` = pwm line (e.g. the MG90S ears on the Pi Zero 2 W: GPIO12/13 = the only hardware-PWM pins left once I2S claims GPIO18-21) |

## Calibration lives here, not in firmware

`params` (global, overridable per channel via `params.per_channel.<name>`):
`freq_hz` (50), `min_us`/`max_us` (500/2500 pulse bounds), `deg_min`/`deg_max`
(travel soft limits), `trim_deg`, `invert`. The firmware's own `min_us`/`max_us`
are *absolute* safety clamps — the soft limits, trim, and the angle→µs map are
the node's meaning, per the firmware-moves-bytes boundary.

Proprioception is the dual sensor: `sensors/servo_feedback` reads the
(divided!) pot taps back as degrees — commanded-vs-measured divergence is the
seam for a future stall-guard policy.

Power: servos run from their own V+ rail (common ground, never the MCU rail);
on the neocore2 that rail is gated by the `power_rail` effector and measured by
the ACS712 (`sensors/current`).

```bash
pytest effectors/servo/ -v     # angle map, clamps, both backends; no hardware
```
