# node/routers/ — HTTP / SSE / WebSocket route handlers

FastAPI routers mounted by `node/app.py` (one `include_router` line each). Every
router reads `request.app.state.{sensors,effectors,policies,devices,relay}` at
request time — **never** a module-level global or a `register_*()` function.

| Router | Surface |
|--------|---------|
| `sensors.py` | `/sensors`, `/sensors/{id}` (+ `/stream` SSE, `/ws`, `/frames` WS) |
| `effectors.py` | `/effectors[/{id}]`, `POST /effectors/{id}` (request), `WS /effectors/{id}/stream` |
| `policies.py` | `/policies[/{id}]`, `POST /policies/{id}/enable` |
| `camera.py` | `/camera` MJPEG stream + camera lifecycle helpers |
| `i2c.py` | `/i2c` bus scan |
| `ir_xcvr.py`, `vl53l1x.py` | sensor-type-specific routes |

A sensor needs a dedicated router only for type-specific actions beyond the base
read API (e.g. IR transmit). See `CLAUDE.md` → "Routers ... use request.app.state".
