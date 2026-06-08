# curve — max-linear reflex policy

A simple always-on control loop: drive every target channel by a curve over
normalized observations. `params`: `in_min[]`, `in_max[]` (aligned with
`observation`), `out_min`, `out_max`. Default `max_linear`:
`drive = out_min + (out_max-out_min) · maxᵢ clamp((xᵢ-in_minᵢ)/(in_maxᵢ-in_minᵢ), 0, 1)`.

Missing inputs are ignored — an absent sensor never forces high output (fail-safe).
This is the chassis-fan reflex (drive fans on the worse of gas and board temp).

```yaml
policies:
  - id: fan_loop
    type: curve
    always_on: true
    observation: [gas_array.raw.mq135, board_temp.cpu_c]
    action: {effector: chassis_fans}
    params: {in_min: [100, 35], in_max: [600, 75], out_min: 0.2, out_max: 1.0}
```
