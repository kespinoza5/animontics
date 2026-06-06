# analog_in — heterogeneous analog inputs (via ADS1115)

Individual analog inputs read through an `Ads1115Device` on the SBC's own I2C bus.
Unlike an array sensor, **each channel is its own signal** with its own meaning and
calibration — e.g. four different sources on one Pi02W ADS1115 (battery voltage, a
current sense, a pot, …). It polls each configured channel and emits raw counts
always, plus a calibrated value per `linear` channel.

In-tree (not a submodule): a generic SBC-side utility with no independent lifecycle.

```
sensors/analog_in/
├── __init__.py   ← METADATA (connectionless; device-fed)
└── sensor.py     ← @register("analog_in") AnalogIn(SensorBase)
```

## Configuration

Declare the ADS1115 as a device, then one `analog_in` sensor whose channels point
at it (`device` + `index`); calibration is per channel.

```yaml
# config/boards/<node>.yaml  (gitignored)
devices:
  - {id: head_adc, kind: ads1115, bus: 1, address: 0x48}
sensors:
  - id: rig
    type: analog_in
    channels:
      - {device: head_adc, index: 0, signal: batt_v,  calibration: {type: linear, scale: 0.002, offset: 0.0, gain: 1}}
      - {device: head_adc, index: 1, signal: current, calibration: {type: raw, gain: 2}}
```

- `calibration: {type: raw}` — raw counts only (always present).
- `calibration: {type: linear, scale, offset}` — also emit `value = count·scale + offset`.
- `gain` (optional) — the ADS1115 PGA index for that channel.

## Data format

```json
{"sensor_id": "rig", "sensor_type": "analog_in",
 "data": {"raw": {"batt_v": 1850, "current": 320}, "batt_v": 3.7}}
```

`raw` is always present; a top-level key appears per `linear` channel.

## Tests

```bash
pytest sensors/analog_in/ -v      # poll + calibration; no hardware (fake device)
```
