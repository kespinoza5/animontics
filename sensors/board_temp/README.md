# board_temp — SBC board/CPU temperature

Reads the SBC's own Linux thermal zones (`/sys/class/thermal/thermal_zone*/temp`).
No external hardware, no device — a connectionless sensor. Emits one key per zone
(`zone0_c`, `zone1_c`, …) plus `cpu_c` (the primary, zone 0). A common input to a
cooling-control policy (e.g. the fan loop runs on the worse of gas and `cpu_c`).

In-tree (not a submodule): trivial and SBC-native.

```
sensors/board_temp/
├── __init__.py   ← METADATA (connectionless)
└── sensor.py     ← @register("board_temp") BoardTemp(SensorBase)
```

## Configuration

```yaml
# config/boards/<node>.yaml
sensors:
  - {id: board_temp, type: board_temp}
```

No connection or device — it reads sysfs directly. On a non-Linux dev box (no
thermal zones) it simply reports unhealthy and emits nothing.

## Data format

```json
{"sensor_id": "board_temp", "sensor_type": "board_temp",
 "data": {"zone0_c": 47.1, "zone1_c": 45.0, "cpu_c": 47.1}}
```

## Use in a policy

```yaml
policies:
  - id: fan_loop
    type: curve
    always_on: true
    observation: [gas_array.raw.mq135, board_temp.cpu_c]
    action: {effector: chassis_fans}
    params: {in_min: [100, 35], in_max: [600, 75], out_min: 0.2, out_max: 1.0}
```
