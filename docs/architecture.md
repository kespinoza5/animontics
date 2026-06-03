# Architecture

Animontics is a distributed sensor infrastructure for an embodied AI system. Computation nodes are
heterogeneous — SBCs on Gigabit Ethernet, a USB-networked microcomputer, and a cluster of MCUs on
a USB hub — and each runs only the software it needs.

---

## System Topology

```
Gigabit Ethernet Switch
├── OrangePi Zero 2      TF Mini Plus LiDAR (UART)
│   └── Pi Zero 2W       (USB gadget)    LV-MaxSonar-EZ (UART)
├── Raspberry Pi 5       MLX90640 Thermal + Webcam
│   └── HAILO-10H hat    (NPU inference accelerator)
├── NeoCore2
│   └── USB Hub
│       ├── RP2040 (power/reboot control for all boards)
│       ├── RP2040 (IMU)
│       ├── SAMD20
│       ├── Arduino
│       └── Feather M4
└── Nvidia Jetson Nano   (CUDA inference)

FPGA fabric: SPI/I2S to multiple boards
             reconfigured via NeoCore2 + RP2040 power controllers
```

Node IPs and SSH access details live in `config/animon.yaml` (gitignored).

Each Linux SBC runs an **animontics node agent** — a lightweight FastAPI HTTP server that exposes
its local sensors over a simple streaming API. The Pi Zero 2W connects to the OrangePi over USB
ethernet gadget and runs its own node agent, reachable from any GbE node.

MCUs (RP2040, SAMD20, etc.) appear to the NeoCore2 as USB CDC serial devices. Future node agents
on those boards will serve over USB network or be polled by the NeoCore2 agent.

---

## Configuration Layers

Four layers — each owns exactly its concern, never crossing into another.

| Layer | File | In repo? | Contains |
|-------|------|----------|----------|
| **Node desired state** | `config/nodes/<id>.yaml` | ✅ | Which sensors each node should run (id + type), capabilities, role |
| **Fleet access** | `config/animon.yaml` | ❌ gitignored | IPs, SSH users — how to reach each board |
| **Board wiring** | `config/boards/<id>.yaml` + board's `config.yaml` | ❌ gitignored | Physical connection details (port, bus, baud, address) |
| **Hardware constraints** | `sensors/<type>/__init__.py` METADATA | ✅ | Valid connection types, locked baud rates, I2C addresses, defaults |

The separation reflects the fundamental distinction between **node** (a logical participant in
the system with a role and sensor responsibilities) and **board** (a physical device with wires
on specific pins). Desired state is versioned because it's a design decision; wiring and access
details are gitignored because they're hardware-specific and may contain network topology.

`animon deploy` negotiates all four layers:

1. Read `config/nodes/<id>.yaml` — what sensors this node should have
2. Read `config/animon.yaml` — how to reach the board
3. Read `config/boards/<id>.yaml` (staging copy) or fetch live `config.yaml` via SSH
4. Reconcile: keep existing wiring, bootstrap new sensors from METADATA defaults, disable removed ones
5. Write merged config to board; update `config/boards/<id>.yaml` staging copy

### METADATA shape

Every sensor `__init__.py` must expose a `METADATA` dict:

```python
METADATA = {
    "type": "tf_mini",
    "name": "TF Mini Plus LiDAR",
    "description": "UART distance sensor, 0.1–12 m range.",
    "connection": {
        "supported": ["uart"],
        "defaults": {"baud_rate": 115200},
        "valid":    {"baud_rate": [115200]},   # locked by hardware
    },
    "data_keys": {
        "distance_mm": "int — measured distance in millimetres",
        "strength":    "int — signal strength (0–65535)",
        "temp_c":      "float — chip temperature",
    },
}
```

Without `METADATA`, `animon deploy` raises `ReconcileError` when adding the sensor to a board
that has no existing `config.yaml` entry — the fleet tool cannot choose defaults without it.

---

## Node Agent

```
config.yaml
    │
    ▼
load_node_config()
    │  reads + validates YAML with Pydantic
    ▼
sensors/__init__.py        ← pkgutil auto-discovers packages present on disk
    │  imports each package → @register fires → registry populated
    ▼
registry.create(sc)        ← one instance per enabled sensor in config
    │
    ▼
SensorBase.start()         ← opens hardware port/bus, starts background thread
    │
    ├─► background thread reads hardware in loop
    │       │
    │       ▼
    │   SensorReading (Pydantic)  ──► SensorBase._broadcast()
    │                                       │
    │                              Broadcaster.broadcast()
    │                                       │
    │                     ┌────────────────┴────────────────┐
    │                     ▼                                 ▼
    │              queue (SSE/WS)                    queue (WS binary)
    │                     │                                 │
    ▼                     ▼                                 ▼
FastAPI app      /sensors/{id}/stream            /sensors/{id}/frames
                 /sensors/{id}/ws
```

High-rate array/image sensors (e.g. thermal) use the binary frame lane instead of — or in
addition to — the JSON lane. See [Data Lanes](#data-lanes) below.

---

## Plugin System

Each sensor type is a self-contained Python package. Adding a new sensor type requires no
changes to the app — only the new package directory needs to exist on the board.

```
sensors/
├── __init__.py         ← pkgutil auto-discovery
├── tf_mini/
│   ├── driver.py       ← hardware protocol only (no threading, no HTTP)
│   ├── sensor.py       ← @register("tf_mini") class TFminiSensor(SensorBase)
│   └── ...
└── my_new_sensor/      ← drop in, restart, done
    ├── driver.py
    ├── sensor.py       ← @register("my_new_sensor")
    └── ...
```

**Discovery:** `sensors/__init__.py` uses `pkgutil.iter_modules` at import time. Every subdirectory
present on disk is imported. Missing hardware dependencies (`smbus2`, `pyserial`, etc.) raise
`ImportError` which is caught and logged — the board doesn't crash.

**Selective deployment:** `animon deploy` reconciles the board's config, extracts the enabled
sensor types, and rsyncs only those package directories (removing any that are no longer needed).
A board running only LiDAR has only `sensors/tf_mini/` on disk — the thermal driver code is never
present on it.

**Custom HTTP routes:** Some sensors need dedicated control endpoints beyond the standard
`/sensors/{id}/*` pattern (e.g. VL53L1X ranging mode, IR transmit). These go in
`node/routers/<type>.py` and are wired in `node/app.py` with a single `include_router()` call.
Routers always access the sensor registry via `request.app.state.sensors` at request time — never
via a module-level dict or a `register_sensors()` helper.

---

## Data Lanes

Two transport lanes serve different sensor profiles:

| Lane | Endpoint | Format | For |
|------|----------|--------|-----|
| **JSON** | `GET /sensors/{id}/stream` (SSE) | `SensorReading` per event | Scalars, events, low-rate |
| **JSON** | `WS /sensors/{id}/ws` | `SensorReading` per message | Same, bidirectional |
| **Binary** | `WS /sensors/{id}/frames` | Packed bytes, sensor-defined | Arrays/images at tens of fps |

### JSON lane

The standard lane. Every sensor produces `SensorReading` objects:

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

The SSE stream also supports **named events** for out-of-band signals (e.g. a sensor reporting
a mode change). Sensors emit them via `self._broadcast_event("mode", {...})`. Browser clients
subscribe with `EventSource.addEventListener("mode", handler)` — the standard `onmessage`
handler receives only unnamed `data:` events.

### Binary frame lane

High-rate sensors that produce array or image data (thermal cameras, pressure grids) opt into the
binary lane by setting `produces_frames = True` and calling `self._broadcast_frame(bytes)`.

The binary lane uses a `FrameBroadcaster` with **latest-wins** backpressure: if a client's queue
is full (capacity 2), the oldest frame is dropped so new frames are never blocked. This keeps
thermal and camera pipelines flowing under CPU load. Compare to the standard `Broadcaster` which
drops slow clients entirely.

Zero-length WebSocket messages are keepalives and carry no frame data — clients must ignore them.

**MLX90640 frame layout** (little-endian):

```
Offset  Type        Field
0       uint32      frame_id (wraps at 2^32)
4       float32     min_temp (°C)
8       float32     max_temp (°C)
12      float32×768 pixel temperatures row-major, 32×24
```

Total: 3084 bytes per frame. The lean JSON reading on the standard lane carries only
`{min_temp, max_temp, width, height}` — pixel arrays are not JSON-serialised at 32 fps.

---

## Browser Viewers

Diagnostic viewers for development and benching live in `web/viewers/`, opened from a dev machine
over `file://` and pointed at any node by IP:

```
web/
├── shared/
│   ├── viewer.css      ← dark theme, layout shell (body, conn-bar, status, btn)
│   ├── stream.js       ← AnimStream — SSE envelope parsing + auto-reconnect
│   └── timeseries.js   ← AnimChart — rolling Chart.js line chart + ring buffer
└── viewers/
    ├── tf_mini.html        distance / scalar
    ├── lv_maxsonar.html    distance / scalar
    ├── vl53l1x.html        distance + Short/Medium/Long/Auto range controls
    ├── mlx90640.html       thermal heatmap (binary frame lane)
    └── ir_xcvr.html        IR receive log + transmit panel
```

Shared JS files are classic globals (`window.AnimStream`, `window.AnimChart`) loaded via
`<script src>`. ES module `import`/`export` is CORS-blocked over `file://` — browsers refuse to
load cross-origin modules from the filesystem regardless of MIME type.

**Viewer archetypes:**

- **Scalar/timeseries** — AnimStream (SSE) + AnimChart. Copy `tf_mini.html`.
- **Scalar + controls** — same, plus buttons that POST to sensor-specific routes and listen for
  named SSE events (`namedEvents: ["mode"]`) to sync state. Copy `vl53l1x.html`.
- **Array/heatmap** — binary WebSocket to `/sensors/{id}/frames`, canvas rendering. Copy
  `mlx90640.html`.
- **Event log** — AnimStream (SSE) + scrolling log table + command panel. Copy `ir_xcvr.html`.

---

## Fleet Management

The fleet CLI (`tools/fleet/animon.py`) manages the distributed system from a single desired-state
file. Key commands:

```
animon status  [<node-id>]     show live sensor health across nodes
animon diff    <node-id>       show drift between desired state and board reality
animon deploy  <node-id>       push changes (--dry-run to preview)
animon pull    <node-id>       fetch live config from board → update boards/ staging + nodes/
animon probe   <node-id>       scan I2C buses and USB ports on the board
```

Exit codes: `0` = success/in-sync, `1` = error, `2` = drift detected (useful in CI).

The deploy process:

1. Load `config/nodes/<id>.yaml` — desired sensors for this node
2. Load `config/animon.yaml` — SSH credentials and IP (gitignored; never committed)
3. Read `config/boards/<id>.yaml` staging copy, or SSH to board for live `config.yaml`
4. Reconcile: keep existing wiring, bootstrap new sensors from METADATA defaults, disable removed ones
5. Rsync only the sensor packages referenced by the resulting config
6. Write merged config to board's `config.yaml`; update `config/boards/<id>.yaml` staging copy
7. Restart the node service

SSH uses key auth only (`BatchMode=yes`). Credentials never appear on the command line.

---

## Git Structure

```
animontics/             parent repo
sensors/tf_mini/        git submodule — independent history (migrated from TFmini/)
sensors/lv_maxsonar/    git submodule (migrated from LV-MaxSonar-EZ/)
sensors/vl53l1x/        git submodule (migrated from VL53L1X/)
sensors/mlx90640/       git submodule (migrated from Thermal/)
sensors/ir_xcvr/        git submodule
tools/usb/usbport/      git submodule (standalone USB-NET tool)
```

Each sensor package has its own commit history. New sensors are created as independent git repos
and registered as submodules — never as plain directories in the parent repo. Deleting a sensor
directory without first preserving its history with `git filter-repo` is permanently destructive.

See `CONTRIBUTING.md` for the full new-sensor walkthrough.
