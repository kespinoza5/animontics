# Contributing to Animontics

## Adding a New Sensor

Each sensor type is a self-contained Python package under `sensors/`. Adding a new
type requires creating a package directory (as a git submodule), writing four files,
and updating three places in the repo.

### 1. Create the package as a git submodule

```bash
# From the project root
git init sensors/my_sensor
cd sensors/my_sensor
# ... add files, initial commit
cd ../..
git submodule add ./sensors/my_sensor sensors/my_sensor
```

Directory layout:

```
sensors/my_sensor/
├── __init__.py     ← METADATA dict + platform-safe import
├── driver.py       ← low-level hardware protocol, no HTTP or threading
├── sensor.py       ← SensorBase implementation with @register
├── README.md       ← hardware wiring, config example, data format
└── test_*.py       ← unit tests (codec/parsing logic, no hardware needed)

web/viewers/my_sensor.html   ← bench viewer (centralized, not in the package)
```

The bench viewer lives in the repo-root `web/` tree, not the sensor package:
it's opened from a dev machine and points at any node, and it shares
`web/shared/` (viewer.css + AnimStream; AnimChart for line charts). See the
existing viewers for the archetype closest to your sensor — distance/scalar
(`tf_mini`), heatmap over the binary frame lane (`mlx90640`), or event log
(`ir_xcvr`).

### 2. Write `driver.py`

Pure hardware communication. No threading, no HTTP, no global state.
Import all hardware-specific libraries inside functions so the module
loads cleanly on development machines without the hardware present.

```python
# sensors/my_sensor/driver.py

def open_device(port: str, baud_rate: int): ...
def read_frame(fd) -> bytes | None: ...
def parse_frame(raw: bytes) -> tuple[int, float] | None:
    """Returns (value, quality) or None on bad frame."""
    ...
def close_device(fd): ...
```

### 3. Write `sensor.py`

```python
# sensors/my_sensor/sensor.py
from __future__ import annotations
import threading
import time
from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
import sensors.my_sensor.driver as _drv

@register("my_sensor")           # ← key used in config.yaml and animon.yaml
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
        return self._latest   # set by SensorBase._broadcast()

    def is_healthy(self) -> bool:
        return self._healthy

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                fd = _drv.open_device(
                    self.config.connection.port,
                    self.config.connection.baud_rate,
                )
                self._healthy = True
                try:
                    while not self._stop.is_set():
                        raw = _drv.read_frame(fd)
                        if raw is None:
                            continue
                        value, quality = _drv.parse_frame(raw)
                        reading = SensorReading(
                            sensor_id=self.id,
                            sensor_type="my_sensor",
                            timestamp=time.time(),
                            data={"distance_mm": value, "strength": quality},
                        )
                        self._broadcast(reading)   # stores _latest + pushes to SSE/WS
                finally:
                    _drv.close_device(fd)
            except Exception as exc:
                self._healthy = False
                self._stop.wait(2)   # retry after 2 s
```

### 4. Write `__init__.py`

**This file has two required parts: a try/except import and a METADATA dict.**

```python
# sensors/my_sensor/__init__.py

try:
    from sensors.my_sensor.sensor import MySensor
except ImportError:
    pass  # hardware deps not available on Windows dev machines

#: Hardware constraints and defaults for the fleet tool.
#: Connection details (actual port / bus / address) live in the board's config.yaml.
METADATA = {
    "type": "my_sensor",
    "name": "My Sensor Full Name",
    "description": "One-line description of what it measures.",
    "connection": {
        # All connection types this sensor can use:
        "supported": ["uart"],        # or ["i2c"], ["uart", "usb_cdc"], ["ir"], etc.
        # Defaults used by 'animon deploy' when no config.yaml exists on the board yet:
        "defaults": {
            "baud_rate": 115200,
        },
        # Hard constraints — deploy will warn if the config violates these:
        "valid": {
            "baud_rate": [115200],    # omit key if any value is valid
        },
    },
    "data_keys": {
        "distance_mm": "int   — measured distance in millimetres",
        "strength":    "int   — signal quality / return strength",
    },
}

__all__ = ["MySensor", "METADATA"]
```

**Why try/except?** Platform-specific libraries (`smbus2`, `fcntl`, serial
drivers) are not available on Windows. The import block must not crash on a
dev machine — `sensors/__init__.py` catches and skips failed packages.

**Why METADATA?** The fleet tool (`animon deploy`) reads METADATA to build a
default `config.yaml` on a fresh board. Without it, deploy raises `ReconcileError`.

### 5. Add the sensor to the node's desired-state file

Edit the relevant node file in `config/nodes/`:

```yaml
# config/nodes/my_node.yaml
sensors:
  - id: my_sensor_1
    type: my_sensor
```

This file is in the repo (no secrets — just id and type). The physical wiring
(port, bus, address) goes into `config/boards/<node-id>.yaml` on your dev machine
(gitignored) or is generated by `animon deploy` from METADATA defaults.

### 6. Add a docs page

Create `docs/sensors/my_sensor.md`:

```markdown
\{%
  include-markdown "../../sensors/my_sensor/README.md"
  rewrite-relative-urls=true
%\}
```

Add it to the Sensors nav in `mkdocs.yml`:

```yaml
  - Sensors:
    - ...
    - My Sensor: sensors/my_sensor.md
```

### 7. Deploy to a board

```bash
python -m tools.fleet.animon deploy <node-id> --dry-run   # preview
python -m tools.fleet.animon deploy <node-id>             # apply
```

---

## Adding a sensor-specific HTTP route

Some sensors need routes beyond the standard SSE/WS streams (e.g. a transmit
endpoint for `ir_xcvr`, a set-mode endpoint for VL53L1X ranging). Add a router
in `node/routers/`:

```python
# node/routers/my_sensor.py
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/my_sensor", tags=["my_sensor"])

def _get_sensor(request: Request):
    sensors = getattr(request.app.state, "sensors", {})
    for s in sensors.values():
        if s.config.type == "my_sensor":
            return s
    raise HTTPException(status_code=404, detail="No my_sensor configured on this node")

@router.post("/action")
async def do_action(request: Request):
    sensor = _get_sensor(request)
    ...
```

Wire it in `node/app.py` — one line only:

```python
from node.routers.my_sensor import router as my_sensor_router
app.include_router(my_sensor_router)
```

**Do not** add a `register_sensors()` function to the router or a call for it in
`app.py`. Use `request.app.state.sensors` at request time instead — this is the
established pattern for all routers.

---

## Adding an MCU target / firmware module

Microcontrollers are built and flashed with `tools/forge`, not deployed like
Python sensors. Firmware is *composed* at build time from a per-instance contract
plus reusable source modules. See [docs/forge.md](docs/forge.md) for the design.

**Keep the boundary:** firmware streams raw bytes; all meaning (calibration,
units, curves) lives in the node-side Python sensor. A firmware module never
interprets its samples.

### Add a module to an existing family (e.g. `mcu/arduino/`)

A module is a hand-written lean C++ library plus a manifest and jinja fragments:

```
mcu/arduino/modules/my_module/
├── manifest.yaml      # platforms, role, claims{kind}, provides{channels}, config, sources
├── my_module.h        # a small class — setup() + its work method(s), no framing
├── my_module.cpp
├── decl.j2            # instance declaration   → main.ino globals
├── setup.j2           # init call              → setup()
└── read.j2 | loop.j2 | send.j2   # role-specific body → loop()
```

`manifest.yaml` shape:

```yaml
module: my_module
platforms: [arduino]
role: sensor              # sensor | actuator | transport
claims: {kind: adc}       # pins must be valid <kind> pins in platform.yaml; one claim per pin
provides: {channels: per_pin}   # sensors only: per_pin or an integer count
config: {sample_hz: 2}    # defaults, overridable per instance in the contract
sources: [my_module.h, my_module.cpp]
```

Fragments render with a uniform context: `inst`, `pins` (Arduino-translated),
`params`, `offset` (this module's first channel index), `count`, `channel_count`,
`baud`. The composer buckets each fragment into `main.ino` — no per-module logic
lives in the builder. Validate with `python -m tools.forge.forge validate <id>`.

### Add a new family or target category

- A new **family** (e.g. `mcu/samd21/`) is another source tree with its own
  `platform.yaml` + modules, driven by the existing `ArduinoBuilder`-style flow.
- A new **category** (FPGA, accelerator) is a new `Builder` subclass in
  `tools/forge/builders/` registered with `@register_builder("fpga.ice40")` and
  imported in `tools/forge/builders/__init__.py`. Implement `validate / compose /
  build / deploy`; nothing else in forge changes.

### Surfacing the data on a node

An MCU that streams channels is read by an **array sensor** that subclasses
`core.analog_array.AnalogArrayBase` (see `sensors/mq_array/`). The base owns the
serial loop and frame decode (`core/mcu_link.py`); your subclass overrides
`enrich()` to add calibrated values on top of the always-present raw lane. Follow
the normal [new-sensor steps](#adding-a-new-sensor) for that package.

## Standardized data keys

All sensors should emit readings with these standardized keys where applicable.

| Category | Required keys | Optional keys |
|----------|---------------|---------------|
| Distance | `distance_mm: int` | `strength: int`, `temp_c: float` |
| Thermal array | `pixels: list[float]` (row-major), `min_temp: float`, `max_temp: float`, `width: int`, `height: int` | — |
| IR remote | `protocol: str`, `address: int`, `command: int`, `scancode: int`, `repeat: bool` | — |
| IMU | `accel_x/y/z: float`, `gyro_x/y/z: float` | `temp_c: float` |
| Pressure | `pressure_pa: float` | `temp_c: float` |

Use `None` for optional fields the hardware does not provide.

---

## Code style

- Type hints everywhere (`from __future__ import annotations` at top of every file)
- Comments only for non-obvious **why** — hardware quirks, calibration constants, protocol workarounds
- No comments explaining what the code does — names and structure should do that
- No global state in sensor packages; all state lives on the sensor instance
- `driver.py` has no side effects on import — pure functions and classes only
- Hardware-specific imports always inside `try/except ImportError` in `__init__.py`
