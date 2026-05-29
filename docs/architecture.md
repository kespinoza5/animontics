# Architecture

Animontics is a distributed sensor infrastructure for an embodied AI system. Computation nodes are heterogeneous — SBCs on Gigabit Ethernet, a USB-networked microcomputer, and a cluster of MCUs on a USB hub — and each runs only the software it needs.

## System Topology

```
Gigabit Ethernet Switch
├── OrangePi Zero 2      192.168.1.x   TF Mini Plus LiDAR (UART)
│   └── Pi Zero 2W       (USB gadget)    LV-MaxSonar-EZ (UART)
├── Raspberry Pi 5       192.168.1.y   MLX90640 Thermal + Webcam
│   └── HAILO-10H hat                   (NPU inference accelerator)
├── NeoCore2             192.168.1.z
│   └── USB Hub
│       ├── RP2040 (power/reboot control for all boards)
│       ├── RP2040 (IMU)
│       ├── SAMD20
│       ├── Arduino
│       └── Feather M4
└── Nvidia Jetson Nano   192.168.1.w   (CUDA inference)

FPGA fabric: SPI/I2S to multiple boards
             reconfigured via NeoCore2 + RP2040 power controllers
```

Each Linux SBC runs an **animontics node agent** — a lightweight FastAPI HTTP server that exposes its local sensors over a simple streaming API. The Pi Zero 2W connects to the OrangePi over USB ethernet gadget and runs its own node agent, reachable from any GbE node.

MCUs (RP2040, SAMD20, etc.) appear to the NeoCore2 as USB CDC serial devices. Future node agents on those boards will serve over USB network or be polled by the NeoCore2 agent.

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
    │                         ┌────────────┴────────────┐
    │                         ▼                         ▼
    │                    queue (SSE)             queue (WebSocket)
    │                         │                         │
    ▼                         ▼                         ▼
FastAPI app            /sensors/{id}/stream     /sensors/{id}/ws
```

## Plugin System

Each sensor type is a self-contained Python package. Adding a new sensor type requires no changes to the app — only the new package directory needs to exist on the board.

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

**Discovery:** `sensors/__init__.py` uses `pkgutil.iter_modules` at import time. Every subdirectory present on disk is imported. Missing hardware dependencies (`smbus2`, `pyserial`, etc.) raise `ImportError` which is caught and logged at DEBUG — the board doesn't crash.

**Selective deployment:** `tools/maintenance/deploy.sh` reads the board's `config.yaml`, extracts enabled sensor types, and rsyncs only those package directories. A board running only LiDAR has only `sensors/tf_mini/` on disk — the thermal driver code is never there.

## Data Flow

All sensor data flows outward as `SensorReading` JSON objects:

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

Clients consume readings via:

- **SSE** (`GET /sensors/{id}/stream`) — recommended for browser-based viewers and dashboards
- **WebSocket** (`WS /sensors/{id}/ws`) — for bidirectional or low-latency clients
- **Polling** (`GET /sensors/{id}`) — latest reading on demand

The `Broadcaster` class manages a queue-per-client. When the sensor thread produces a reading, `broadcast()` pushes it to all subscribed queues simultaneously. Stale queues from disconnected clients are pruned automatically on the next broadcast.

## Configuration Layers

| Layer | File | Lives | Purpose |
|-------|------|-------|---------|
| Per-board | `config.yaml` | On the board, gitignored | What this node loads and runs |
| Fleet | `fleet.yaml` | In the repo | Whole-system topology reference |

The fleet config does not control any server at runtime. It documents the system for developers and future management tooling.

## Git Structure

```
animontics/             parent repo
sensors/tf_mini/        git submodule — independent history
sensors/lv_maxsonar/    git submodule
sensors/vl53l1x/        git submodule
sensors/mlx90640/       git submodule
tools/usb/usbport/      git submodule (standalone USB-NET tool)
```

Each sensor package has its own commit history, starting with the original standalone Flask server and showing the migration to the `SensorBase` plugin architecture. Future sensors should be created as independent git repos and registered as submodules.
