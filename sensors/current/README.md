# current — rail current via hall-effect sensors (ACS712)

Interoception: how hard is the body working, and is anything about to burn?
An ACS712-30A sits inline on the servo V+ rail; its analog output (Vcc/2 at
zero current, 66 mV/A) is read as raw counts through the neocore2's 5 V
ADS1115 (`visceral_adc`) and converted to signed amps here.

```
servo V+ rail → ACS712 → ADS1115 (VDD=5 V, shifted I2C) → device frames → current → SSE
```

Device-fed `AnalogArrayBase` subclass — no `connection`, no driver.

## Calibration

`{type: acs712, zero_counts, counts_per_amp}` per channel:

```
amps = (count - zero_counts) / counts_per_amp        (signed)
```

- `zero_counts` — captured at bench with the load off (Vcc/2 drifts with the
  sensor's actual supply; don't compute it, measure it).
- `counts_per_amp` — the sensor's mV/A (66 for the 30 A part) × the ADC's
  counts/mV at the configured PGA gain.

## The overcurrent reflex

The published `amps` signal (`rail_current.amps.servo_rail` on the thalamic
relay) is the observation of the `threshold` guard policy that cuts the
`power_rail` effector — three DS3218s can stall at ~2.5–3 A each, so the rail
is sized, measured, and guarded as one system. See
`effectors/power_rail/README.md` for the full loop.

## Data format

```json
{"sensor_id": "rail_current", "sensor_type": "current",
 "data": {"seq": 3, "raw": {"servo_rail": 14002}, "amps": {"servo_rail": 2.0}}}
```

## Tests

```bash
pytest sensors/current/ -v     # calibration math, signed flow; no hardware
```
