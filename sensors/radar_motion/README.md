# radar_motion — microwave Doppler motion (RCWL-0516, analog-hacked)

Distal motion sense: a pair of RCWL-0516 microwave radars, hacked to expose
the analog Doppler stage instead of the stock 2 s digital pulse, read through
the neocore2's 5 V ADS1115 (`visceral_adc`).

```
RCWL-0516 (analog hack) ×2 → ADS1115 (VDD=5 V, shifted I2C) → device frames → radar_motion → SSE
```

Device-fed `AnalogArrayBase` subclass — no `connection`, no driver. The
firmware/device ships raw counts; the meaning (what counts as motion) lives
here:

- a slow EMA **baseline** tracks each channel's resting level
  (`params.baseline_alpha`, default 0.02) — but only adapts while quiescent,
  so a person standing in the field is never absorbed into "resting";
- `level` = |count − baseline| and `motion` = `level > params.threshold`
  (default 500 counts — **VERIFY at bench** against the hack's actual gain).

A natural future reflex: `motion` gating attention or waking gated subsystems
via the relay (`motion_1.motion.radar_fore` is a normal thalamic signal).

## Data format

```json
{"sensor_id": "motion_1", "sensor_type": "radar_motion",
 "data": {"seq": 9, "raw": {"radar_fore": 12950, "radar_aft": 11400},
          "level": {"radar_fore": 950.0, "radar_aft": 12.0},
          "motion": {"radar_fore": true, "radar_aft": false}}}
```

## Tests

```bash
pytest sensors/radar_motion/ -v   # baseline seeding, trip, drift tracking; no hardware
```
