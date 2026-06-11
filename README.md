# Animontics

A distributed **nervous system** for an embodied AI. Each compute node is a
*cortex*: it **senses** the world (afferent), **acts** on it through **effectors**
(efferent — motion, light, sound), and runs local **control loops** (policies),
all over a lightweight HTTP server. Sensors and effectors reach hardware through
**devices** (shared peripherals); the microcontrollers behind them run firmware
**composed by `forge`**. The system spans Linux SBCs over Gigabit Ethernet, a
USB-networked Pi Zero 2W, and a cluster of CircuitPython/MicroPython
microcontrollers on a USB hub.

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

Start at **Architecture** for the system design, **The Cortex Runtime** for the
node model (devices/sensors/effectors/policies), **Firmware & Targets (forge)**
for the microcontroller tier, or **Getting Started** for a first deploy. The
source pages live in `docs/` and the navigation is defined in `mkdocs.yml`.

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

Every board runs the same node agent (`node/app.py`, FastAPI). On startup it
brings up its **cortex runtime** — devices → sensors → effectors → relay →
policies — and serves them over HTTP. You don't manage boards by hand: the
**fleet CLI** (`animon`) keeps each board's code and config in sync from a single
desired-state file on your dev machine, and the **firmware CLI** (`forge`)
composes the microcontroller firmware behind the devices.

Sensor configuration is split into four layers, each owning exactly one concern:

| Layer | Where | In repo? | Holds |
|-------|-------|----------|-------|
| **Desired state** | `config/nodes/<id>.yaml` | ✅ | Which sensors a node runs (id + type), role, capabilities |
| **Fleet access** | `config/animon.yaml` | ❌ | IPs, SSH users — how to reach each board |
| **Board wiring** | `config/boards/<id>.yaml` | ❌ | Physical connections (port, bus, baud, address) |
| **Hardware constraints** | `sensors/<type>/__init__.py` `METADATA` | ✅ | Valid connection types, addresses, locked baud rates |

The board config additionally declares the runtime's other tiers — `devices:`,
`effectors:`, `policies:` — and each microcontroller has a build contract in
`config/mcus/<id>.yaml` that `forge` composes into firmware.

`animon deploy` reconciles desired state against the board's existing wiring,
fills gaps from METADATA defaults, validates, and ships only the packages that
board needs. See **[docs/architecture.md](docs/architecture.md)** for the fleet
design, **[docs/cortex.md](docs/cortex.md)** for the node runtime, and
**[docs/forge.md](docs/forge.md)** for firmware composition.

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
python -m node                                    # binds host:port from config.network

# Install as a service (the deploy flow does this for you; ExecStart=python -m node)
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

## Extending the system

See [CONTRIBUTING.md](CONTRIBUTING.md). Each tier follows the same plugin shape —
a base class + registry, declared in config, no wiring edits:

- **Sensor** — implement `SensorBase` (`@register`) — or, for an MCU-fed array,
  subclass `AnalogArrayBase` and just declare `channels`.
- **Effector** — implement `EffectorBase` (`@register_effector`); drive over the
  request and/or stream lane.
- **Policy** — implement `PolicyBase` (`@register_policy`) — `step(obs) → action`.
- **Device** — implement `Device` (`@register_device`) for a new shared peripheral.
- **MCU firmware** — add a `mcu/<family>/` module or family for `forge`.

## Project Layout

```
core/           Cortex runtime + shared infra: SensorBase, AnalogArrayBase, device,
                effector_base, policy, relay, mcu_link, models, registry
sensors/        Sensor plugin packages (submodules; trivial ones in-tree)
  tf_mini/, lv_maxsonar/, vl53l1x/, mlx90640/, ir_xcvr/   distance / thermal / IR
  mq_array/     MQ gas sensor array (via an MCU device)
  pressure_array/  Pressure surface across MCUs (via devices)
  analog_in/    Heterogeneous analog inputs (ADS1115 device) — in-tree
  board_temp/   SBC board/CPU temperature (sysfs) — in-tree
  servo_feedback/  Servo position proprioception (analog pot via ADS1115) — in-tree
  current/      ACS712 current sensing (via ADS1115) — in-tree
  radar_motion/ RCWL-0516 microwave presence — in-tree
  audio_in/     I2S microphone capture — in-tree
effectors/      Effector plugin packages (efferent: pwm, fan_array, servo, power_rail, speaker, stream_sink)
policies/       Policy plugin packages (control loops: curve, threshold)
mcu/            Firmware source by runtime (composed by forge)
  arduino/      compiled C++ (AVR/ATmega328P)
  circuit_python/  generic runtime for CircuitPython boards (XIAO, RP2040)
firmware/       Build output — composed/compiled artifacts (gitignored)
node/           Per-board node agent (FastAPI + uvicorn)
  app.py        App factory: starts devices/sensors/effectors/relay/policies, mounts routers
  routers/      HTTP/SSE/WebSocket route handlers (sensors, effectors, policies, …)
config/         nodes/ + animon.yaml + boards/ wiring + mcus/ firmware contracts
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

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Node info (id, type, hostname, sensor health) |
| `GET` | `/sensors` · `/sensors/{id}` | List / latest reading (JSON) |
| `GET` | `/sensors/{id}/stream` | SSE stream of readings |
| `WS` | `/sensors/{id}/ws` · `/sensors/{id}/frames` | JSON / binary-frame stream |
| `GET` | `/devices` · `/devices/{id}` | Devices: health with gating awareness (healthy / gated / down) |
| `GET` | `/effectors` · `/effectors/{id}` | Outputs: list / descriptor + state |
| `POST` | `/effectors/{id}` | **Drive** the request lane (e.g. pwm `{"levels": {...}}`) |
| `WS` | `/effectors/{id}/stream` | Drive the stream lane (continuous flow) |
| `GET` | `/policies` · `/policies/{id}` | Control loops: list / inspect |
| `POST` | `/policies/{id}/enable` | Enable/disable a policy |
| `GET` | `/config` | The board's running config |
| `GET` | `/camera` · `/i2c` | MJPEG stream / I2C bus scan |
| `GET`·`POST` | `/ir/*` · `/vl53l1x/*` | Type-specific (IR transmit, ToF mode) — see the sensor's page |

Per-sensor diagnostic viewers live in `web/viewers/` (built on the shared modules in `web/shared/`) and open directly in a browser. Point them at any node's IP.

## Deferred Work

See [TODO.md](TODO.md).
