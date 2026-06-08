# fan_array — fan control effector

Drives one or more named fans over the request lane. Built on the generic
[`pwm`](../pwm/README.md) drive (level `0.0–1.0` → device `set_duty`), adding the
fan-specific bit: **per-fan `min_duty`** (fans differ in where they actually
start). `params.per_fan: {<name>: <min_duty>}` overrides the effector-wide
`params.min_duty` for that fan; a non-zero level maps into `[min_duty, 1]`, level
0 is fully off.

```yaml
# config/boards/<node>.yaml
effectors:
  - id: chassis_fans
    type: fan_array
    backend: {device: lxiao}          # the MCU that drives the fan PWM
    params:
      min_duty: 0.3                    # default floor
      per_fan:  {exhaust: 0.5}         # this fan needs more to start
    channels:
      - {name: intake,  index: 0}
      - {name: exhaust, index: 1}
      - {name: aux,     index: 2}
```

Drive: `POST /effectors/chassis_fans {"levels": {"intake": 0.8, "exhaust": 0.4}}`.

RPM lives elsewhere: a paired `fan_tach` sensor publishes RPM to the relay, and
closing the loop (target RPM → trim level) is a **policy**, not this effector.
