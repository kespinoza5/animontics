# pressure_array — pressure sensor surface (via MCU-hosted ADS1115)

A logical array of pressure transducers read as raw ADC over one or more MCU
serial uplinks. The cranial-pressure surface, for example, spans **4 MCUs × 4
ADS1115 = 64 channels** but is exposed as a single logical sensor — devices are
plumbing, not the API's structure.

```
transducers → ADS1115 (×4 per MCU) → CircuitPython MCU → forge link → node device → pressure_array → SSE
```

It is a thin `AnalogArrayBase` subclass: the base subscribes to each device's frame
stream, keeps the latest samples per device, and composes one reading; this package
adds a calibrated kPa value per channel. The MCU firmware is built with
[`tools/forge`](../../docs/forge.md) (the `mcu/circuit_python/` family).

## Configuration

Each channel maps a `device` + frame `index` to a pressure `signal` and its
calibration. A sensor may span several devices.

```yaml
# config/boards/<node>.yaml  (gitignored)
devices:
  - {id: press0, kind: mcu_serial, port: /dev/serial/by-id/…xiao0…, baud: 115200}
  - {id: press1, kind: mcu_serial, port: /dev/serial/by-id/…xiao1…, baud: 115200}
sensors:
  - id: cranial_pressure
    type: pressure_array
    channels:
      - {device: press0, index: 0, signal: cp_00, calibration: {type: linear, scale: 0.1, offset: -5.0}}
      - {device: press0, index: 1, signal: cp_01, calibration: {type: raw}}
      # … through press3 index 15 → cp_63
```

- `calibration: {type: raw}` — raw counts only (always present).
- `calibration: {type: linear, scale, offset}` — also emit `kPa = count·scale + offset`.

## Data format

```json
{
  "sensor_id": "cranial_pressure", "sensor_type": "pressure_array",
  "data": {"seq": 12, "raw": {"cp_00": 412, "cp_01": 388}, "kpa": {"cp_00": 36.2}}
}
```

`raw` is always present; `kpa` appears for `linear` channels.

## Tests

```bash
pytest sensors/pressure_array/ -v      # transfer math + multi-device compose; no hardware
```
