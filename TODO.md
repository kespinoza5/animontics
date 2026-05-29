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

- [ ] `dashboard/` multi-node browser client — connects to multiple board IPs, aggregates sensor cards
- [ ] Shared JS modules: `sensor-stream.js`, `distance-chart.js`, `thermal-canvas.js`
- [ ] Per-sensor `viewer.html` files updated to use shared JS modules
- [ ] Unified `index.html` dashboard with node IP management UI

---

## Tools

- [ ] `tools/board/setup_i2c.sh` — enable I2C, set bus speed via `/boot/config.txt`
- [ ] `tools/board/setup_uart.sh` — enable UART, disable serial console
- [ ] `tools/board/setup_spi.sh` — enable SPI
- [ ] `tools/board/setup_i2s.sh` — enable I2S audio
- [ ] `tools/firmware/flash_circuitpython.sh` — flash RP2040/SAMD20 via UF2
- [ ] `tools/firmware/flash_micropython.sh`
- [ ] `tools/ssh/gen_keys.sh` — generate node SSH key pairs
- [ ] `tools/ssh/distribute_keys.sh` — push public keys to all fleet nodes
- [ ] `tools/maintenance/update_apt.sh`
- [ ] `tools/maintenance/update_pip.sh`

---

## Sensor Packages

- [ ] `sensors/ads1115/` — 16-bit ADC for pressure arrays (16 × ADS1115 via 4 × RP2040)
- [ ] `sensors/imu/` — IMU via RP2040/SAMD20 USB CDC
- [ ] `sensors/camera/` — Generalize `node/routers/camera.py` into a proper SensorBase plugin
- [ ] Per-sensor `firmware/` subdirs with CircuitPython/MicroPython scripts for MCU-hosted sensors

---

## Infrastructure

- [ ] Delete `LV-MaxSonar-EZ/` root directory — access denied on Windows; contents already migrated to `sensors/lv_maxsonar/`; close File Explorer / VS Code on that path first
- [ ] Board profiles (`config/profiles/`) — hardware defaults per board type
- [ ] Fleet node discovery / health check endpoint
- [ ] Hotswap peripheral autodetection (scan I2C + USB on startup, auto-add to config)
- [ ] `docs/ARCHITECTURE.md` — full system design, topology diagram, data flow
- [ ] `docs/API.md` — complete endpoint reference (depends on API design above)
- [ ] `docs/boards/` — per-board wiring and setup guides
- [ ] Register `tools/usb/usbport/` as a git submodule
- [ ] Graft `LV-MaxSonar-EZ/` git history onto `sensors/lv_maxsonar` once Windows permissions are resolved

---

## FPGA

- [ ] FPGA reconfiguration workflow via NeoCore2 + RP2040 power controllers
- [ ] SPI/I2S sensor data path from FPGA to host board
