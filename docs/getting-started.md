# Getting Started

## Prerequisites

- Python 3.11+ on the board
- SSH key auth configured to target boards (no password prompt for deploy scripts)
- `i2c-tools` on boards using I2C sensors (`sudo apt install i2c-tools`)

## On a Board

```bash
# Clone the repo (or use the fleet CLI from your dev machine)
git clone --recurse-submodules https://github.com/your-org/animontics.git /opt/animontics
cd /opt/animontics

# Install dependencies
pip3 install -r requirements.txt

# Create a wiring config for this board
cp config/boards/example.yaml config/boards/<your-node-id>.yaml
nano config/boards/<your-node-id>.yaml   # set node_id, node_type, fill in sensor connections
```

Example wiring config for a board with a TF Mini LiDAR on UART:

```yaml
node_id:   my_sbc_node
node_type: orangepi_zero2
hostname:  animontics-node

network:
  host: "0.0.0.0"
  port: 8080

sensors:
  - id: lidar_front
    type: tf_mini
    enabled: true
    connection:
      type:      uart
      port:      /dev/ttyAMA0
      baud_rate: 115200
```

```bash
# Verify sensors are wired up before starting
./tools/board/verify_comms.sh

# Run the node agent
uvicorn node.app:app --host 0.0.0.0 --port 8080

# Or install as a systemd service
sudo cp animontics-node.service /etc/systemd/system/
sudo systemctl enable --now animontics-node
```

## From Your Development Machine

```bash
# Deploy to a board via the fleet CLI
python -m tools.fleet.animon deploy my_sbc_node

# Preview what deploy will change without touching the board
python -m tools.fleet.animon deploy my_sbc_node --dry-run

# Check live sensor health across all nodes
python -m tools.fleet.animon status

# Verify hardware connections on a remote board
python -m tools.fleet.animon probe my_sbc_node
```

See [Fleet CLI](architecture.md#fleet-management) for the full command reference.

## Reading Sensor Data

Once the node agent is running, sensor data is available at:

```bash
# Latest reading (JSON)
curl http://<board-ip>:8080/sensors/lidar_front

# Node summary (all sensors + health)
curl http://<board-ip>:8080/

# Stream readings (SSE — open in browser or curl)
curl -N http://<board-ip>:8080/sensors/lidar_front/stream
```

Open `web/viewers/tf_mini.html` in a browser, enter the board's IP and sensor id, and you'll get a live chart. The `web/viewers/` tree has a bench viewer for each sensor type.

## Adding a New Sensor

See [Contributing](contributing.md). The short version: create `sensors/my_sensor/` with `driver.py`, `sensor.py` (`@register("my_sensor")`), and `__init__.py`. No other files change. Deploy the directory and enable it in the board's `config.yaml`.

## Building These Docs

```bash
pip install -r docs/requirements.txt
mkdocs serve        # live-reloading local preview at http://localhost:8000
mkdocs build        # static site in site/
```
