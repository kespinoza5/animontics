# pwm — generic PWM effector

Drives one or more named PWM channels through a device's `set_duty` command
(request lane). For LED brightness, unidirectional motor speed, or any 0–1 level
output. Fans have a dedicated [`fan_array`](../fan_array/README.md) type built on
the same drive.

```yaml
# config/boards/<node>.yaml
effectors:
  - id: panel_led
    type: pwm
    backend: {device: lxiao}
    params: {min_duty: 0.0}        # non-zero level → [min_duty, 1]; 0 = off
    channels: [{name: glow, index: 0}]
```

Drive it: `POST /effectors/panel_led {"levels": {"glow": 0.6}}` (level by name or
index). `min_duty` lets loads with a minimum start point actually move.
