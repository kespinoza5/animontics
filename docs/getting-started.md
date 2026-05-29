# Getting Started

## Prerequisites

- Python 3.11+ on the board
- SSH key auth configured to target boards (no password prompt for deploy scripts)
- `i2c-tools` on boards using I2C sensors (`sudo apt install i2c-tools`)

## On a Board

```bash
# Clone the repo (or use deploy.sh from your dev machine)
git clone --recurse-submodules https://github.com/your-org/animontics.git /opt/animontics
cd /opt/animontics

# Install dependencies
pip3 install -r requirements.txt

# Create a config for this board
cp config/config.example.yaml config/config.yaml
nano config/config.yaml        # set node_id, node_type, enable your sensors
```

Example config for a board with a TF Mini LiDAR on UART:

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
# Deploy to a board (reads its config.yaml to decide which packages to copy)
./tools/maintenance/deploy.sh pi@192.168.1.x

# Deploy with a specific config file
./tools/maintenance/deploy.sh pi@192.168.1.y config/rpi5.yaml

# Verify hardware connections on a remote board
ssh pi@192.168.1.x 'bash -s' < tools/board/verify_comms.sh
```

## Reading Sensor Data

Once the node agent is running, sensor data is available at:

```bash
# Latest reading (JSON)
curl http://192.168.1.x:8080/sensors/lidar_front

# Node summary (all sensors + health)
curl http://192.168.1.x:8080/

# Stream readings (SSE — open in browser or curl)
curl -N http://192.168.1.x:8080/sensors/lidar_front/stream
```

Open `sensors/tf_mini/viewer.html` in a browser, enter the board's IP, and you'll get a live chart.

## Adding a New Sensor

See [Contributing](contributing.md). The short version: create `sensors/my_sensor/` with `driver.py`, `sensor.py` (`@register("my_sensor")`), and `__init__.py`. No other files change. Deploy the directory and enable it in the board's `config.yaml`.

## Building These Docs

```bash
pip install -r docs/requirements.txt
mkdocs serve        # live-reloading local preview at http://localhost:8000
mkdocs build        # static site in site/
```
