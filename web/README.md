# web/ — bench viewers

Browser diagnostic viewers for the Animontics sensors. These are **dev-machine
tools**, not served from the boards: you open an HTML file locally (over
`file://`) and point it at any node's IP. One viewer per sensor type.

```
web/
├── shared/                 reused across every viewer
│   ├── viewer.css          dark theme + base shell (body / h1 / btn / conn-bar / status)
│   ├── stream.js           AnimStream — SSE envelope parsing + auto-reconnect
│   └── timeseries.js       AnimChart — rolling Chart.js line chart + ring buffer
└── viewers/
    ├── tf_mini.html        distance / scalar (JSON SSE lane)
    ├── lv_maxsonar.html    distance / scalar
    ├── vl53l1x.html        distance + Short/Medium/Long/Auto range controls
    ├── mlx90640.html       thermal heatmap (binary frame lane)
    └── ir_xcvr.html        IR receive log + transmit panel (event-log archetype)
```

## Using a viewer

1. Open `web/viewers/<type>.html` in a browser (double-click / `file://`).
2. Enter the board IP and the sensor `id` (as configured in the board's
   `config.yaml`), then **Connect**.

The node serves on port **8080**. Viewers read from:

- `GET /sensors/<id>/stream` — SSE, one JSON `SensorReading` per event
  (`{sensor_id, sensor_type, timestamp, data}`). Used by scalar/event viewers.
- `ws://<host>:8080/sensors/<id>/frames` — binary frame stream for high-rate
  array/image sensors (thermal, pressure grids). Used by the heatmap viewer.

## Two transports

| Lane | Endpoint | For | Server cost |
|------|----------|-----|-------------|
| JSON | `/sensors/<id>/stream` (SSE), `/ws` | scalars, events, low-rate | `json.dumps` per reading |
| Binary | `/sensors/<id>/frames` (WS) | arrays/images at tens of fps | packed bytes, no JSON |

A sensor opts into the binary lane by setting `produces_frames = True` and
calling `self._broadcast_frame(bytes)` (see `sensors/mlx90640/sensor.py`); its
frame layout is documented in that sensor's README.

## Why classic scripts, not ES modules

`web/shared/*.js` expose globals (`window.AnimStream`, `window.AnimChart`) and
load via `<script src>`. Browsers block ES-module `import`/`export` over
`file://` (CORS), and these viewers must run straight off disk with no server.

## Adding a viewer

Copy the archetype closest to your sensor, link `../shared/viewer.css`, pull in
`../shared/stream.js` (+ `../shared/timeseries.js` for line charts), and keep
only the per-sensor config (units, thresholds, controls) in the page. See
`CONTRIBUTING.md`.
