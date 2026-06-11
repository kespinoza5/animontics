# pressure_array — pressure sensor surface (via MCU-hosted ADS1115)

A logical array of pressure transducers read as raw ADC over one or more MCU
serial uplinks, exposed as a single logical sensor — devices are plumbing, not
the API's structure. Two shapes:

- **Flat array** — every channel is a static tap (e.g. a cranial surface
  spanning 4 MCUs × 4 ADS1115 = 64 channels).
- **Scanned lattice** — a velostat matrix energized one row at a time: a
  conductor MCU drives CD4051 row muxes and coordinates follower MCUs over an
  analog DAC handshake (`mcu/circuit_python/modules/matrix_scan` /
  `scan_follower`); every device frame carries the row index in a `row_tag`
  channel, and this sensor reassembles full rows × columns sweeps.

```
velostat rows ← CD4051 ← conductor MCU ─┐
taps → ADS1115 / native ADC → followers ─┴→ forge link → node device(s) → pressure_array → SSE + frames
```

It is an `AnalogArrayBase` subclass: the base subscribes to each device's frame
stream and composes readings; this package adds kPa calibration, and — in
lattice mode — row-aligned sweep assembly. The MCU firmware is built with
[`tools/forge`](../../docs/forge.md) (the `mcu/circuit_python/` family).

## Configuration

Each channel maps a `device` + frame `index` to a `signal` and its calibration.
A sensor may span several devices. Channels are filled from the MCU contracts
by `forge resolve <node>` — author the map once, in `config/mcus/<id>.yaml`.

```yaml
# config/boards/<node>.yaml  (gitignored)
devices:
  - {id: featherm4_lattice, kind: mcu_serial, port: /dev/serial/by-id/…m4…,    baud: 115200}
  - {id: samd21_press0,     kind: mcu_serial, port: /dev/serial/by-id/…xiao0…, baud: 115200}
sensors:
  - id: pressure_1
    type: pressure_array
    devices: [featherm4_lattice, samd21_press0]   # → forge resolve fills channels
    params:
      rows: 16                                    # lattice mode; omit for a flat array
    channels:
      - {device: featherm4_lattice, index: 0, signal: cnd_row, calibration: {type: row_tag}}
      - {device: featherm4_lattice, index: 1, signal: cnd00,   calibration: {type: raw}}
      # … one row_tag per device, then its data channels
```

- `calibration: {type: raw}` — raw counts only (always present).
- `calibration: {type: linear, scale, offset}` — also emit `kPa = count·scale + offset`.
- `calibration: {type: row_tag}` — this channel is the device's scan-row index
  (lattice mode; the firmware emits -1 when a follower loses the conductor).

## Data format

JSON lane (light — scalars + diagnostics):

```json
{
  "sensor_id": "pressure_1", "sensor_type": "pressure_array",
  "data": {
    "seq": 12, "raw": {"cnd00": 412, "ant00": 388}, "kpa": {"cnd00": 36.2},
    "row": {"featherm4_lattice": 7, "samd21_press0": 7},
    "sweep": {"n": 41, "rows": 16, "cols": 84, "complete": true,
              "missing_cells": 0, "timeouts": 0,
              "devices": ["featherm4_lattice", "samd21_press0"]}
  }
}
```

Binary frame lane (`WS /sensors/<id>/frames`, lattice mode): one frame per
completed sweep — header `<IHHff>` = (sweep_n, rows, cols, min, max) followed
by `rows × cols` little-endian float32, row-major, columns in config channel
order, **NaN** for cells a device never delivered. A device that laps the
others (e.g. a dead follower) forces a partial sweep with `complete: false` —
degradation is visible, never silent.

## Tests

```bash
pytest sensors/pressure_array/ -v      # transfer math, multi-device compose,
                                       # sweep assembly + sentinels; no hardware
```
