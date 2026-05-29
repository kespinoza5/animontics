# node

Per-board node agent. Loads configuration, starts enabled sensors, and serves the HTTP API.

## Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app factory and lifespan manager |
| `routers/sensors.py` | Sensor REST + SSE + WebSocket endpoints |
| `routers/camera.py` | MJPEG camera stream endpoint |
| `routers/i2c.py` | I2C bus scan endpoint |

## Running

```bash
# From the animontics root directory
uvicorn node.app:app --host 0.0.0.0 --port 8080

# With a custom config path
ANIMONTICS_CONFIG=/path/to/config.yaml uvicorn node.app:app --host 0.0.0.0 --port 8080

# As a systemd service (see animontics-node.service)
sudo systemctl start animontics-node
```

## Startup Sequence

```
1. load_node_config(config.yaml)         ← reads and validates YAML
2. import sensors                        ← auto-discovers sensor packages on disk
3. for each enabled sensor in config:
     sensor = registry.create(sc)        ← instantiates via @register key
     sensor.start()                      ← opens hardware, starts background thread
4. start_camera() if camera.enabled
5. FastAPI begins serving requests
```

On shutdown the lifespan context manager stops all sensors and releases hardware.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Node identity and sensor health summary |
| `GET` | `/sensors` | List all configured sensors |
| `GET` | `/sensors/{id}` | Latest reading from one sensor (JSON) |
| `GET` | `/sensors/{id}/stream` | Server-Sent Events stream (keepalive every 25 s) |
| `WS` | `/sensors/{id}/ws` | WebSocket stream |
| `GET` | `/camera` | MJPEG multipart stream (503 if no camera configured) |
| `GET` | `/i2c` | Scan all I2C buses, return detected addresses |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANIMONTICS_CONFIG` | `config/config.yaml` | Path to the per-board config file |
