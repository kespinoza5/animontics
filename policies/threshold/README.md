# threshold — guard reflex (trip / release with hysteresis)

An always-on guard: when any observed signal exceeds `trip_above`, drive the
target effector to 0 (off); re-arm to 1 only when **all** signals fall below
`release_below`. With `latch: true` a trip is permanent until the policy is
re-enabled or the node restarts — the right default for an overcurrent cut,
where the cause should be inspected before power returns.

The canonical instance is the **overcurrent reflex** on the neocore2: the
ACS712 (`sensors/current`, `rail_current.amps.servo_rail`) guards the servo
V+ rail (`effectors/power_rail`):

```yaml
policies:
  - id: overcurrent_guard
    type: threshold
    always_on: true
    observation: [rail_current.amps.servo_rail]
    action: {effector: servo_rail}
    params:
      trip_above: 8.0       # A — above any sane multi-servo transient
      release_below: 0.5    # A — only near idle (ignored when latched)
      latch: true
```

Design choices: actions are emitted **only on transitions**, so the guard
never fights manual rail control between events; missing observations never
trip (an absent sensor is not an emergency) and never release.
