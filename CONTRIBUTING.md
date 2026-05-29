# Contributing to Animontics

## Adding a New Sensor

Each sensor type is a self-contained Python package under `sensors/`. Adding a new type requires four files and one line change.

### 1. Create the package directory

```
sensors/
└── my_sensor/
    ├── __init__.py
    ├── driver.py      ← low-level hardware protocol, no HTTP or threading
    ├── sensor.py      ← SensorBase implementation with @register
    ├── viewer.html    ← desktop diagnostic viewer
    └── README.md
```

### 2. Write `driver.py`

Pure hardware communication. No threading, no HTTP, no global state. Returns parsed values or raises exceptions.

```python
# sensors/my_sensor/driver.py

def parse_frame(raw: bytes) -> tuple[int, float] | None:
    """Parse a raw sensor frame. Returns (value, quality) or None on bad frame."""
    ...
```

### 3. Write `sensor.py`

```python
# sensors/my_sensor/sensor.py
from __future__ import annotations
import threading, time
from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
from sensors.my_sensor.driver import parse_frame

@register("my_sensor")           # ← key used in config.yaml
class MySensor(SensorBase):

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        self._stop = threading.Event()
        self._healthy = False

    def start(self) -> None:
        self._stop.clear()
        threading.Thread(target=self._loop, daemon=True, name=f"sensor-{self.id}").start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                # ... open hardware, read, call self._broadcast(reading)
                reading = SensorReading(
                    sensor_id=self.id,
                    sensor_type="my_sensor",
                    timestamp=time.time(),
                    data={"distance_mm": 1234},
                )
                self._broadcast(reading)
            except Exception as exc:
                self._healthy = False
                self._stop.wait(2)
```

### 4. Write `__init__.py`

```python
from sensors.my_sensor.sensor import MySensor
__all__ = ["MySensor"]
```

### 5. That's it

The sensor is auto-discovered by `sensors/__init__.py` via `pkgutil`. No changes needed to `node/app.py` or any other file.

Enable it in a board's `config.yaml`:

```yaml
sensors:
  - id: my_sensor_1
    type: my_sensor
    enabled: true
    connection:
      type: uart
      port: /dev/ttyACM0
      baud_rate: 115200
```

Deploy the package to the board:

```bash
./tools/maintenance/deploy.sh pi@<board-ip>
```

---

## Standardized Data Keys

All sensors should emit readings with these standardized keys where applicable.

| Sensor category | Required keys | Optional keys |
|-----------------|---------------|---------------|
| Distance | `distance_mm: int` | `strength: int`, `temp_c: float` |
| Thermal array | `pixels: list[float]`, `min_temp: float`, `max_temp: float`, `width: int`, `height: int` | — |
| IMU | `accel_x/y/z: float`, `gyro_x/y/z: float` | `temp_c: float` |
| Pressure | `pressure_pa: float` | `temp_c: float` |

Use `None` for optional fields that the hardware does not provide.

---

## Code Style

- Type hints everywhere (use `from __future__ import annotations`)
- No comments explaining what the code does — names should do that
- Comments only for non-obvious WHY: hardware quirks, calibration magic, workarounds
- No global state in sensor packages; all state lives on the sensor instance
- `driver.py` has no side effects on import — pure functions and classes only
