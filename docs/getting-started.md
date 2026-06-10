# Getting Started

Boards are provisioned **from your dev machine** through the fleet CLI — you do
not clone this repo onto each board. You declare what a node should run in a
committed desired-state file, and `animon deploy` ships only the code and config
that board needs. Read [Architecture](architecture.md) for the full design and
[Configuration](config.md) for the four-layer model; this page is the shortest
path to a running node.

## Prerequisites

**On your dev machine:**

- Python 3.11+, plus `rsync` and an SSH client
- A fleet SSH key, generated and pushed to the boards (see below) — the CLI uses
  key auth only and never prompts for a password

**On each board (one-time prep):**

- Python 3.11+
- The hardware buses your sensors use, enabled
- `i2c-tools` for I2C sensors (`sudo apt install i2c-tools`)

## 1. Set up SSH access (dev machine)

Generate a dedicated fleet key and install it on the boards. After this, the CLI
can reach every node with key auth.

```bash
./tools/ssh/gen_keys.sh                 # creates ~/.ssh/animontics_ed25519
ssh-add ~/.ssh/animontics_ed25519
./tools/ssh/distribute_keys.sh          # ssh-copy-id to every node in animon.yaml
```

`distribute_keys.sh` reads `config/animon.yaml` (set up in step 3); for a board
not yet listed there, run `ssh-copy-id <user>@<board-ip>` by hand for the first
deploy. See [SSH Access](tools/ssh.md) for key rotation and optional hardening.

## 2. Prepare the board (on the board)

Enable the interfaces your sensors use, then confirm the hardware is visible.
These edit the firmware `config.txt` idempotently and need a reboot.

```bash
sudo ./tools/board/setup_uart.sh        # UART sensors (TF Mini, LV-MaxSonar)
sudo ./tools/board/setup_i2c.sh         # I2C sensors (VL53L1X, MLX90640)
sudo reboot

./tools/board/verify_comms.sh           # scan I2C / UART / USB — confirm wiring
```

See [Board Setup & Comms](tools/board.md) for `setup_spi.sh`, `setup_i2s.sh`,
and I2C bus-speed options.

## 3. Declare the node and deploy (dev machine)

Two committed-vs-local files drive a deploy:

```bash
# Desired state — what this node runs (committed, no secrets: id + type only)
cp config/nodes/example.yaml config/nodes/my_sbc_node.yaml
$EDITOR config/nodes/my_sbc_node.yaml

# Access — how to reach the board (gitignored: IPs, SSH users)
cp config/animon.example.yaml config/animon.yaml
$EDITOR config/animon.yaml
```

A minimal desired-state file — note there are **no wiring details** here (port,
bus, baud, address). Those are bootstrapped from each sensor's METADATA defaults,
or read from the board's existing wiring, and recorded in the gitignored
`config/boards/<id>.yaml` after deploy:

```yaml
# config/nodes/my_sbc_node.yaml — pure desired state (no network/address)
id:    my_sbc_node
type:  raspberry_pi_5
role:  vision

sensors:
  - id: lidar_front
    type: tf_mini
  - id: thermal_rear
    type: mlx90640
```

The node's address (hostname + the HTTP `port`) is access info — it lives in
`config/animon.yaml` alongside the IP and SSH user, not here.

Preview, then deploy:

```bash
python -m tools.fleet.animon diff   my_sbc_node   # what would change — nothing transferred
python -m tools.fleet.animon deploy my_sbc_node   # reconcile, validate, rsync, restart, health-check
python -m tools.fleet.animon status               # live health across the fleet
python -m tools.fleet.animon probe  my_sbc_node   # detect connected hardware on the board
```

**Bootstrap a board not yet in `animon.yaml`** — the desired-state file is
enough; point `deploy` at the address directly. The full reconcile + validate +
health-check still runs.

```bash
python -m tools.fleet.animon deploy my_sbc_node --host 192.168.1.50 --user pi
# then record the board in config/animon.yaml so node-id alone works afterward
```

See the [Fleet CLI](tools/fleet.md) for `deploy`, `status`, `diff`, `pull`,
`probe`, `revert`, and ad-hoc config overrides.

## Reading Sensor Data

Once the node agent is running, sensor data is available over HTTP:

```bash
# Latest reading (JSON)
curl http://<board-ip>:8080/sensors/lidar_front

# Node summary (all sensors + health)
curl http://<board-ip>:8080/

# Stream readings (SSE — open in a browser or curl)
curl -N http://<board-ip>:8080/sensors/lidar_front/stream
```

Open `web/viewers/tf_mini.html` in a browser, enter the board's IP and sensor id,
and you'll get a live chart. The `web/viewers/` tree has a bench viewer for each
sensor type.

## Running a node directly (local development)

For local testing — or on a board, skipping the CLI — you can run the agent
yourself. It reads `config/config.yaml`:

```bash
pip3 install -r requirements.txt
python -m node                       # binds host:port from config.network

# Or install as a systemd service (the deploy flow does this for you)
sudo cp animontics-node.service /etc/systemd/system/
sudo systemctl enable --now animontics-node
```

## Adding a New Sensor

See [Contributing](contributing.md). The short version: create
`sensors/my_sensor/` with `driver.py`, `sensor.py` (`@register("my_sensor")`),
and `__init__.py` (with `METADATA`). Add the `{id, type}` to the node's
`config/nodes/<id>.yaml` and `animon deploy` ships the new package — no other
files change.

## Building These Docs

```bash
pip install -r docs/requirements.txt
python -m mkdocs serve        # live-reloading local preview at http://localhost:8000
python -m mkdocs build        # static site in site/
```
