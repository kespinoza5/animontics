# Animontics

Distributed sensor infrastructure for an embodied AI system. Each compute node runs a lightweight HTTP server exposing its local sensors. The system spans Linux SBCs connected over Gigabit Ethernet, a USB-networked Pi Zero 2W, and a cluster of CircuitPython/MicroPython microcontrollers on a USB hub.

## Hardware Topology

```
Gigabit Ethernet Switch
├── OrangePi Zero 2      TF Mini Plus LiDAR (UART)
│   └── Pi Zero 2W       (USB gadget)    LV-MaxSonar-EZ (UART)
├── Raspberry Pi 5       MLX90640 Thermal + Camera
│   └── HAILO-10H NPU hat               (inference accelerator)
├── NeoCore2
│   └── USB Hub → RP2040 × N, SAMD20 × N, Arduino, Feather M4
│       (RP2040s control power/reboot for all boards)
└── Nvidia Jetson Nano   (CUDA inference)

FPGA fabric: SPI/I2S connections to multiple boards
             reconfigured via NeoCore2 over USB
```

Node IPs, SSH users, and access details live in `config/animon.yaml` (gitignored).
See `config/animon.example.yaml` for the schema.

## Quick Start

### On a board

```bash
# Clone the repo
git clone https://github.com/your-org/animontics.git /opt/animontics
cd /opt/animontics

# Install dependencies
pip3 install -r requirements.txt

# Configure this board
cp config/boards/example.yaml config/boards/<your-node-id>.yaml
nano config/boards/<your-node-id>.yaml   # set node_id, fill in connection details

# Run the node agent
uvicorn node.app:app --host 0.0.0.0 --port 8080

# Or install as a service
sudo cp animontics-node.service /etc/systemd/system/
sudo systemctl enable --now animontics-node
```

### From your development machine

```bash
# Deploy to a board via the fleet CLI
python -m tools.fleet.animon deploy my_sbc_node

# Verify hardware connections on a board
python -m tools.fleet.animon probe my_sbc_node
```

## Adding a New Sensor

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version: create a package under `sensors/`, implement `SensorBase`, add `@register("my_type")`, and enable it in `config.yaml`. No other files change.

## Project Layout

```
core/           Shared infrastructure: SensorBase, models, config loader, registry
sensors/        Sensor plugin packages (each its own git repo)
  tf_mini/      Benewake TF Mini Plus LiDAR
  lv_maxsonar/  MaxBotix LV-MaxSonar-EZ ultrasonic
  vl53l1x/      ST VL53L1X time-of-flight
  mlx90640/     Melexis MLX90640 32×24 thermal array
node/           Per-board node agent (FastAPI + uvicorn)
  app.py        App factory: loads config, starts sensors, mounts routers
  routers/      HTTP/SSE/WebSocket route handlers
config/         Per-board config.yaml + animon.yaml fleet topology
tools/          Board management and provisioning scripts
  usb/usbport/  USB ethernet interface tool (standalone)
  network/      WiFi AP setup scripts
  board/        Hardware interface verification
  maintenance/  Deploy and update scripts
```

## API

Each node exposes:

| Endpoint | Description |
|----------|-------------|
| `GET /` | Node info (id, type, hostname, sensor health) |
| `GET /sensors` | List of configured sensors |
| `GET /sensors/{id}` | Latest reading (JSON) |
| `GET /sensors/{id}/stream` | SSE stream of readings |
| `WS /sensors/{id}/ws` | WebSocket stream |
| `GET /camera` | MJPEG stream (if camera enabled) |
| `GET /i2c` | I2C bus scan |

Per-sensor diagnostic viewers live in each sensor package directory and open directly in a browser. Point them at any node's IP.

## Deferred Work

See [TODO.md](TODO.md).
