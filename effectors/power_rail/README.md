# power_rail — switchable power rail (gated ≠ failed)

Switches one power rail — an SRD-05VDC relay on the servo V+ rail, a high-side
switch, a brainstem power line — over the request lane:
`POST /effectors/<id>` with `{"on": false}` (or the policy lane's
`{"levels": {<channel>: 0|1}}`, which is how the overcurrent guard drives it).

## Backends

| `backend` | Drives |
|-----------|--------|
| `{kind: gpio, line: {backend: libgpiod, chip, line, active_low}}` | SBC kernel GPIO on the relay IN pin. Most SRD-05VDC modules energize on **LOW** — express that as `active_low: true` in the line spec, so `on` always means "rail powered". |
| `{kind: mcu, device: <id>, channel: N}` | a `gpio_out` firmware channel through the device's command sink (`core/gpio.py` mcu backend) — the seam the Waveshare RP2040 **brainstem** controllers use for every SBC/MCU power/reset line |

## Gated ≠ failed

`params.members` names the device ids powered *through* this rail. While the
rail is off those devices are **gated**: `GET /devices` reports
`gated: true` instead of letting them read as faults, and the `mcu_serial`
reconnect loop (2 s backoff) re-adopts them when power returns. A deliberate
power cut is a body state, not an error.

Rail state is published to the thalamic relay as **`power.<id>`** (1/0), so
policies and future cross-cortex tracts observe gating like any other signal.

## The overcurrent reflex

Pair with `sensors/current` (ACS712 inline on the same rail) and a
`policies/threshold` guard:

```yaml
policies:
  - id: overcurrent_guard
    type: threshold
    always_on: true
    observation: [rail_current.amps.servo_rail]
    action: {effector: servo_rail}
    params: {trip_above: 8.0, release_below: 0.5, latch: true}
```

`initial: "on"` (default) applies at startup; node shutdown deliberately
leaves the rail as-is — restarting the agent must never cut power.

```bash
pytest effectors/power_rail/ -v     # switching, gating, both backends; no hardware
```
