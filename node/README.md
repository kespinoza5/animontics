# node

Per-board node agent (a "cortex"): loads configuration, starts the runtime tiers —
**devices, sensors, effectors, policies** wired through the **relay** — and serves
the HTTP API. See [docs/cortex.md](../docs/cortex.md) for the runtime model.

## Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app factory + lifespan (devices → sensors → effectors → relay → policies) |
| `routers/sensors.py` | Sensor REST + SSE + WebSocket endpoints |
| `routers/effectors.py` | Effector list/state + request (POST) and stream (WS) drive |
| `routers/policies.py` | Policy list/state + enable/disable |
| `routers/camera.py` | MJPEG camera stream endpoint |
| `routers/i2c.py` | I2C bus scan endpoint |
| `routers/{ir_xcvr,vl53l1x}.py` | sensor-type-specific routes |

Each router reads `request.app.state.{sensors,effectors,policies,devices,relay}`.

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
3. start devices                         ← shared peripherals (MCU links, ADS1115)
4. create sensors; attach_devices; start ← device-fed sensors bind their devices
5. create effectors; attach_devices      ← outputs bind their backend device
6. relay + create policies               ← PolicyRuntime starts ticking the stack
7. start_camera() if camera.enabled
8. FastAPI begins serving requests
```

On shutdown the lifespan stops policies → effectors → sensors → devices, then the
camera, releasing hardware in reverse order.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Node identity and sensor health summary |
| `GET` | `/sensors` | List all configured sensors |
| `GET` | `/sensors/{id}` | Latest reading from one sensor (JSON) |
| `GET` | `/sensors/{id}/stream` | Server-Sent Events stream (keepalive every 25 s) |
| `WS` | `/sensors/{id}/ws` | WebSocket JSON reading stream |
| `WS` | `/sensors/{id}/frames` | Binary frame stream (high-rate array sensors) |
| `GET` | `/effectors` · `/effectors/{id}` | Effector list / descriptor + cached state |
| `POST` | `/effectors/{id}` | Request-lane drive (type-defined body, e.g. pwm levels) |
| `WS` | `/effectors/{id}/stream` | Stream-lane drive (continuous flow) |
| `GET` | `/policies` · `/policies/{id}` | Policy list / wiring + current obs & action |
| `POST` | `/policies/{id}/enable` | Enable/disable a policy |
| `GET` | `/config` | The board's running configuration |
| `GET` | `/camera` | MJPEG multipart stream (503 if no camera configured) |
| `GET` | `/i2c` | Scan all I2C buses, return detected addresses |
| `GET`/`POST` | `/ir/*` | IR transceiver: `capabilities`, `protocols`, `transmit` |
| `GET`/`POST` | `/vl53l1x/*` | ToF control: `state`, `mode`, `auto` |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANIMONTICS_CONFIG` | `config/config.yaml` | Path to the per-board config file |
