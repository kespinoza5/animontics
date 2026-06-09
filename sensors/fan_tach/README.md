# fan_tach — fan RPM (via MCU tach counters)

Fan RPM read from a CircuitPython MCU's tach (FG) inputs. The firmware
`tach` module (see `mcu/circuit_python/modules/tach/`) counts FG edges
and converts to RPM, streaming it in the uplink frame; this sensor surfaces it.
Because the fans are 4-pin (V+/GND always powered), FG is valid at any PWM duty —
so the same MCU (the LXiao) drives the fans (`fan_array` effector) **and** reports
their RPM here.

In-tree (a thin `AnalogArrayBase` subclass — the raw frame value *is* RPM, no
calibration; `enrich` aliases it under `rpm`).

## Configuration

```yaml
# config/boards/<node>.yaml
sensors:
  - id: fan_rpm
    type: fan_tach
    devices: [lxiao]        # forge resolve derives the RPM channels from the contract
```

`forge resolve <node>` fills `channels` from the LXiao's contract (its `tach`
module's signals, in wire order) — author the channel→signal map once in
`config/mcus/lxiao.yaml`. An explicit `channels` list still works as an override.

## Data format

```json
{"sensor_id": "fan_rpm", "sensor_type": "fan_tach",
 "data": {"seq": 9, "raw": {"intake": 5400, "exhaust": 4980}, "rpm": {"intake": 5400, "exhaust": 4980}}}
```

A policy can read these RPMs from the relay to close the loop on a `fan_array`.
