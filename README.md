# Animontics

Distributed sensor infrastructure for an embodied AI system. Each compute node runs a lightweight HTTP server exposing its local sensors. The system spans Linux SBCs connected over Gigabit Ethernet, a USB-networked Pi Zero 2W, and a cluster of CircuitPython/MicroPython microcontrollers on a USB hub.

## Documentation

The full project documentation — architecture, configuration model, per-sensor
guides, the fleet CLI, and an auto-generated API reference — is a browsable
[MkDocs](https://www.mkdocs.org/) site built from the `docs/` tree.

```bash
# Install the docs toolchain (one time)
pip install -r docs/requirements.txt

# Serve locally with live reload, then open http://127.0.0.1:8000
python -m mkdocs serve

# Or build the static site into ./site/
python -m mkdocs build
```

Start at **Architecture** for the system design, or **Getting Started** for a
first deploy. The source pages live in `docs/` and the navigation is defined in
`mkdocs.yml`.

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

## How It Works

Every board runs the same node agent (`node/app.py`, FastAPI) and serves only
the sensors assigned to it. You don't manage boards by hand — the **fleet CLI**
(`animon`) keeps each board's code and config in sync from a single desired-state
file on your dev machine.

Configuration is split into four layers, each owning exactly one concern:

| Layer | Where | In repo? | Holds |
|-------|-------|----------|-------|
| **Desired state** | `config/nodes/<id>.yaml` | ✅ | Which sensors a node runs (id + type), role, capabilities |
| **Fleet access** | `config/animon.yaml` | ❌ | IPs, SSH users — how to reach each board |
| **Board wiring** | `config/boards/<id>.yaml` | ❌ | Physical connections (port, bus, baud, address) |
| **Hardware constraints** | `sensors/<type>/__init__.py` `METADATA` | ✅ | Valid connection types, addresses, locked baud rates |

`animon deploy` negotiates all four: it reconciles the desired state against the
board's existing wiring, fills gaps from METADATA defaults, validates the result,
and ships only the sensor packages that board actually needs.

See **[docs/architecture.md](docs/architecture.md)** for the full design —
topology, configuration layers, the sensor plugin system, data lanes, and the
fleet deploy flow.

## Quick Start

Boards are provisioned from a dev machine — you don't clone the repo onto each
one. Drive everything through the fleet CLI:

```bash
# 1. Declare what the node should run (committed, no secrets)
$EDITOR config/nodes/my_sbc_node.yaml      # see config/nodes/example.yaml

# 2. Tell the CLI how to reach the board (gitignored)
$EDITOR config/animon.yaml                  # see config/animon.example.yaml

# 3. Preview, then deploy
python -m tools.fleet.animon diff   my_sbc_node
python -m tools.fleet.animon deploy my_sbc_node

# Check live health across the fleet, or detect hardware on a board
python -m tools.fleet.animon status
python -m tools.fleet.animon probe  my_sbc_node
```

First touch — a board not yet in `config/animon.yaml`? Bootstrap it by address;
the full reconcile/validate flow still runs:

```bash
python -m tools.fleet.animon deploy my_sbc_node --host <board-ip> --user pi
```

See the [Fleet CLI guide](tools/fleet/README.md) for `deploy`, `status`, `diff`,
`pull`, `probe`, `revert`, and ad-hoc config overrides for testing/rollback.

### Running a node directly (local development)

On a board (or for local testing) you can skip the CLI and run the agent itself:

```bash
pip3 install -r requirements.txt
uvicorn node.app:app --host 0.0.0.0 --port 8080   # reads config/config.yaml

# Install as a service (the deploy flow does this for you)
sudo cp animontics-node.service /etc/systemd/system/
sudo systemctl enable --now animontics-node
```

## Tools

Everything is driven from your dev machine — no per-board logins for day-to-day
work. The tools are grouped by concern:

| Tool | Command | What it's for |
|------|---------|---------------|
| **Fleet CLI** | `python -m tools.fleet.animon` | Keep boards in sync from desired state — `deploy`, `status`, `diff`, `pull`, `probe`, `revert`. The primary interface. See [tools/fleet/README.md](tools/fleet/README.md). |
| **Firmware (forge)** | `python -m tools.forge.forge` | Compose + compile + flash microcontroller firmware from a contract — `validate`, `build`, `flash`, `clean`. The MCU-tier counterpart to `animon`. See [tools/forge/README.md](tools/forge/README.md) and [docs/forge.md](docs/forge.md). |
| **Repo audit** | `python tools/dev/audit.py` | Conformance checks — verifies sensor packages and routers follow the plugin contract (METADATA present, no `register_sensors` anti-pattern). Static analysis, safe to run on any OS. |
| **SSH access** | `tools/ssh/fleet_access.sh setup` | One command to generate the Ed25519 fleet key, push it to every board in `animon.yaml`, and write `~/.ssh/config` aliases so `ssh`/`scp <node-id>` just work (no `-i`, no `ssh-add`) — the key auth the CLI requires. Also `refresh`, `rotate`, and `--harden` to disable board password auth. Run on your dev machine. |
| **Board setup** | `tools/board/setup_{i2c,uart,spi,i2s}.sh` | Enable a hardware bus on the board (idempotent edits to `config.txt`; run as root, reboot after). Raspberry Pi OS. |
| **Comms check** | `tools/board/verify_comms.sh` | On-board scan of I2C buses and UART/USB devices — sanity-check wiring before deploy. |
| **WiFi AP** | `tools/network/setup_ap.sh` / `undo_ap.sh` | Bring a board up as / down from a WiFi access point. |
| **USB networking** | `tools/usb/usbport/` | Standalone USB-ethernet interface tool for the USB-gadget Pi Zero link. |

Start with the [Tools overview](tools/README.md) for what each one does and when
to reach for it; the [Fleet CLI guide](tools/fleet/README.md) covers the `animon`
subcommands in depth, including ad-hoc config overrides and `revert`.

## Adding a New Sensor

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version: create a package under `sensors/`, implement `SensorBase`, add `@register("my_type")`, and enable it in `config.yaml`. No other files change.

## Project Layout

```
core/           Cortex runtime + shared infra: SensorBase, AnalogArrayBase, device,
                effector_base, policy, relay, mcu_link, models, registry
sensors/        Sensor plugin packages (each its own git repo)
  tf_mini/      Benewake TF Mini Plus LiDAR
  lv_maxsonar/  MaxBotix LV-MaxSonar-EZ ultrasonic
  vl53l1x/      ST VL53L1X time-of-flight
  mlx90640/     Melexis MLX90640 32×24 thermal array
  mq_array/     MQ gas sensor array (read over an MCU serial uplink)
mcu/            Firmware source by chip family (composed by forge)
  arduino/      platform.yaml, modules/, templates/ for AVR/Arduino targets
firmware/       Build output — composed + compiled artifacts (gitignored)
node/           Per-board node agent (FastAPI + uvicorn)
  app.py        App factory: loads config, starts sensors, mounts routers
  routers/      HTTP/SSE/WebSocket route handlers
config/         Per-board config.yaml + animon.yaml fleet topology + mcus/ contracts
tools/          Board management and provisioning scripts
  fleet/        animon CLI — deploy, status, diff, pull, probe
  forge/        forge CLI — compose/compile/flash MCU firmware
  ssh/          Fleet SSH access — key gen/distribute/rotate, ~/.ssh/config setup
  dev/          Repo audit / conformance checks
  usb/usbport/  USB ethernet interface tool (standalone)
  network/      WiFi AP setup scripts
  board/        Hardware interface verification
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

Per-sensor diagnostic viewers live in `web/viewers/` (built on the shared modules in `web/shared/`) and open directly in a browser. Point them at any node's IP.

## Deferred Work

See [TODO.md](TODO.md).
