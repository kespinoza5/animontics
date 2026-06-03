# Animontics — Deferred Work

Items not yet implemented. Grouped by area.

---

## API Design

The current sensor streaming API (`GET /sensors/{id}/stream`, `WS /sensors/{id}/ws`) is a starting point. Finalize with project team:

- [ ] Multiplexed stream endpoint (all sensors in one connection)?
- [ ] Command/control API (set VL53L1X ranging mode, etc.)?
- [ ] Node-to-node API for aggregator nodes pulling from sensor nodes?
- [ ] Authentication / access control?

---

## Dashboard / Frontend

- [x] Centralized `web/` tree — viewers moved out of the sensor packages into
      `web/viewers/`, opened from a dev machine against any node
- [x] Shared modules in `web/shared/`: `viewer.css`, `stream.js` (`AnimStream`
      SSE helper), `timeseries.js` (`AnimChart` rolling line chart)
- [x] All five viewers rebuilt on the shared modules (tf_mini, lv_maxsonar,
      vl53l1x, mlx90640, ir_xcvr)
- [x] Binary frame lane (`/sensors/<id>/frames`) for high-rate array/image
      sensors; thermal viewer consumes it
- [ ] `web/shared/heatmap.js` — extract the thermal canvas/palette/crosshair
      engine from `mlx90640.html` once a second array sensor (pressure grid) lands
- [ ] Pressure-array viewer (RP2040 → USB CDC) — multi-channel grid archetype
- [ ] `dashboard/` multi-node browser client — connects to multiple board IPs, aggregates sensor cards
- [ ] Unified `index.html` dashboard with node IP management UI

---

## Tools

- [ ] `tools/dev/audit.py` — shape-aware router check: detect module-level mutable dicts
      that handlers close over (the `register_sensors` anti-pattern by another name) rather
      than relying solely on the literal string `"register_sensors"`. Requires AST analysis
      of each router file's module scope.
- [ ] `tools/board/setup_i2c.sh` — enable I2C, set bus speed via `/boot/config.txt`
- [ ] `tools/board/setup_uart.sh` — enable UART, disable serial console
- [ ] `tools/board/setup_spi.sh` — enable SPI
- [ ] `tools/board/setup_i2s.sh` — enable I2S audio
- [ ] `tools/firmware/flash_circuitpython.sh` — flash RP2040/SAMD20 via UF2
- [ ] `tools/firmware/flash_micropython.sh`
- [ ] `tools/ssh/gen_keys.sh` — generate node SSH key pairs
- [ ] `tools/ssh/distribute_keys.sh` — push public keys to all fleet nodes
- [ ] `animon update <node-id>` — remote apt/pip upgrade as a fleet subcommand
      (folded into tools/fleet/ rather than a standalone maintenance script)
- [ ] `tools/fleet/deploy.py` — `deploy --dry-run` still makes one SSH call
      (`_remote_packages`) to compute packages-to-remove, so an offline dry-run
      (e.g. previewing a `--config` override) pauses on the connect timeout.
      Skip the remote query under `dry_run` and report removals as
      "unknown (offline)".

---

## Sensor Packages

- [ ] `sensors/ads1115/` — 16-bit ADC for pressure arrays (16 × ADS1115 via 4 × RP2040)
- [ ] `sensors/imu/` — IMU via RP2040/SAMD20 USB CDC
- [ ] `sensors/camera/` — Generalize `node/routers/camera.py` into a proper SensorBase plugin
- [ ] Per-sensor `firmware/` subdirs with CircuitPython/MicroPython scripts for MCU-hosted sensors

---

## Infrastructure

- [x] Delete `LV-MaxSonar-EZ/` root directory — resolved
- [ ] Board profiles (`config/profiles/`) — hardware defaults per board type
- [ ] Fleet node discovery / health check endpoint
- [ ] Hotswap peripheral autodetection (scan I2C + USB on startup, auto-add to config)
- [x] `docs/architecture.md` — full system design, topology diagram, data flow
- [ ] `docs/API.md` — complete endpoint reference (depends on API design above)
- [ ] `docs/boards/` — per-board wiring and setup guides
- [ ] Register `tools/usb/usbport/` as a git submodule
- [ ] Graft `LV-MaxSonar-EZ/` git history onto `sensors/lv_maxsonar` — directory is gone, can now proceed when desired

---

## FPGA

- [ ] FPGA reconfiguration workflow via NeoCore2 + RP2040 power controllers
- [ ] SPI/I2S sensor data path from FPGA to host board
