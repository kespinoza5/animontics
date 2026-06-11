# servo_feedback — joint proprioception from servo pot taps

The MG90S and DS3218 servos are hacked to expose their position-pot wipers as
analog feedback. This sensor turns those taps into joint angles — the body's
proprioception, and the observation half of any future stall/limit-guard
policy (commanded angle from `effectors/servo` vs. measured angle from here).

```
pot wiper → divider → ADC (MCU analog_in pins, or SBC-side ADS1115) → device frames → servo_feedback → SSE
```

Device-fed `AnalogArrayBase` subclass — no `connection`, no driver; the device
does the I/O. Two instances in the current fleet:

| Instance | Node | Path |
|----------|------|------|
| `neck_feedback` (3× DS3218) | neocore2_hub | cervical SAMD21 `analog_in` A1/A2/A3 → `mcu_serial` |
| `ear_feedback` (2× MG90S) | pizero_auditory | head ADS1115 (VDD = 5 V, shifted I2C) |

## ⚠ Dividers are mandatory

The wiper swings to the servo's V+ rail — **6–7.4 V on a DS3218, 5 V on an
MG90S** — and the SAMD21 ADC is 3.3 V. Divide every tap. The divider ratio is
deliberately *not* configured anywhere: it is absorbed into the calibration
endpoints below, measured at bench.

## Calibration

`{type: servo_pot, counts_min, counts_max, deg_min, deg_max}` per channel:
command the servo to each soft limit, record the counts, author the endpoints.

```
deg = deg_min + (count - counts_min) / (counts_max - counts_min) * (deg_max - deg_min)
```

clamped to `[deg_min, deg_max]`. Raw counts are always emitted alongside.

## Data format

```json
{"sensor_id": "neck_feedback", "sensor_type": "servo_feedback",
 "data": {"seq": 7, "raw": {"yaw": 11000}, "deg": {"yaw": 90.0}}}
```

## Tests

```bash
pytest sensors/servo_feedback/ -v     # calibration + multi-device; no hardware
```
