# core

Shared Python infrastructure for the animontics node agent. No hardware dependencies — importable on any machine.

## Files

| File | Purpose |
|------|---------|
| `sensor_base.py` | `SensorBase` abstract base — all sensor plugins inherit it |
| `analog_array.py` | `AnalogArrayBase` — array sensors bound to 1+ devices (may span MCUs) |
| `device.py` | `Device` base + registry; `McuSerialDevice` (push), `Ads1115Device` (pull) — shared peripherals |
| `effector_base.py` | `EffectorBase` + registry; `PwmEffector` (request lane), `StreamSink` (stream lane) |
| `policy.py` | `PolicyBase` (obs→action) + registry, `CurvePolicy`, `PolicyRuntime` — control loops |
| `relay.py` | `Relay` — the thalamus: named-signal pub/sub + gating; inter-cortex seam |
| `mcu_link.py` | MCU↔node frame codec (sample + command frames) — node decodes; firmware mirrors |
| `broadcaster.py` | `Broadcaster`/`FrameBroadcaster` pub/sub — per sensor, shared across HTTP clients |
| `models.py` | Pydantic models: `SensorReading`/`SensorConfig`/`ConnectionConfig`/`SensorChannel`, `DeviceConfig`, `EffectorConfig`, `PolicyConfig`, `NodeConfig` |
| `registry.py` | `@register` decorator + `create()` factory — the plugin wiring layer |
| `config.py` | `load_node_config()` — reads and validates `config.yaml` |

The device / effector / policy / relay tiers are the **cortex runtime** — see
[docs/cortex.md](../docs/cortex.md). `core/` stays importable on any machine
(hardware libs are imported lazily inside methods).

## How They Fit Together — the cortex runtime

`node/app.py`'s lifespan builds the tiers from `NodeConfig` (each via its own
`@register*` registry) and wires them: devices feed sensors, the relay carries
observations to policies, and policies drive effectors back through devices.

```
config.yaml ─► config.py ─► NodeConfig          (afferent ─────────────► efferent)

  devices ───frames──► sensors ───readings──►┬─► broadcaster ─► HTTP (SSE / WS / REST)
 (device.py:         (sensor_base /          └─► relay (named-signal obs bus)
  McuSerial, Ads1115) analog_array)                 │
       ▲                                            ▼
       │ commands (send_command)        policies ◄──observation──┘
  effectors ◄────────actions───────── (policy.py: step(obs) → action)
 (effector_base: PwmEffector, …)        e.g. the always-on fan reflex
```

The MCU↔node wire format is `mcu_link.py` (the node decodes; firmware mirrors it).
See [docs/cortex.md](../docs/cortex.md) for the full model.

## Implementing a Sensor

```python
from core.registry import register
from core.sensor_base import SensorBase
from core.models import SensorConfig, SensorReading
import time, threading

@register("my_sensor")
class MySensor(SensorBase):

    def start(self) -> None:
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy

    def _loop(self) -> None:
        while not self._stop.is_set():
            reading = SensorReading(
                sensor_id=self.id,
                sensor_type="my_sensor",
                timestamp=time.time(),
                data={"distance_mm": 1234},
            )
            self._broadcast(reading)   # stores latest + pushes to all HTTP subscribers
            self._stop.wait(0.1)
```

Effectors (`EffectorBase` + `@register_effector`), policies (`PolicyBase` +
`@register_policy`), and devices (`Device` + `@register_device`) follow the same
base-class + registry pattern, declared in the board config and built in the
lifespan. See [CONTRIBUTING.md](../CONTRIBUTING.md) for all four and standardized
data keys.

## SensorReading Data Format

```json
{
  "sensor_id":   "lidar_front",
  "sensor_type": "tf_mini",
  "timestamp":   1717000000.0,
  "data": {
    "distance_mm": 843,
    "strength":    512,
    "temp_c":      38.2
  }
}
```

`data` keys are sensor-type specific. Standardized keys per category are defined in [CONTRIBUTING.md](../CONTRIBUTING.md).
