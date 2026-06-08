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
- [x] `tools/board/setup_i2c.sh` — enable I2C, set bus speed via `config.txt`
      (idempotent; `--baudrate`; loads i2c-dev)
- [x] `tools/board/setup_uart.sh` — enable UART, strip serial console from
      cmdline.txt, disable serial-getty
- [x] `tools/board/setup_spi.sh` — enable SPI
- [x] `tools/board/setup_i2s.sh` — enable I2S audio (`--overlay` for device overlays)
- [ ] `tools/board/setup_*.sh` — Armbian/Orange Pi support. The current scripts
      edit Raspberry Pi `config.txt`; Orange Pi Zero 2 uses `armbianEnv.txt` +
      overlays (`armbian-config`). Add a parallel path or detect the platform.
- [~] `tools/firmware/flash_*.sh` — SUPERSEDED by `tools/forge`. Firmware is
      composed + compiled + flashed from a contract (`config/mcus/<id>.yaml`)
      rather than hand-flashed by per-runtime scripts. See `docs/forge.md`.
- [ ] `tools/forge/test_raw.py`-style collection hazard: bare `pytest` at the
      repo root crashes on `sensors/*/test_raw.py` (interactive hardware scripts
      that `sys.exit` on import). Rename them to `*_raw_check.py` or add a
      `conftest.py` `collect_ignore_glob` so the root suite is runnable.
- [x] `tools/ssh/gen_keys.sh` — generate a dedicated Ed25519 fleet key pair
- [x] `tools/ssh/distribute_keys.sh` — ssh-copy-id the fleet key to every node
      in `animon.yaml`; `--harden`/`--unharden` toggle board password auth
- [x] `tools/ssh/revoke_keys.sh` — remove a fleet public key from boards
      (key rotation / revocation); refuses to empty authorized_keys without --force
- [x] `tools/ssh/setup_ssh_config.sh` — generate a managed ~/.ssh/config block
      from animon.yaml so `scp/ssh <node-id>` work with no -i / no ssh-add
- [x] `tools/ssh/fleet_access.sh` — one wrapper stitching gen/distribute/config/
      revoke into setup / refresh / rotate workflows; auto-detects python3 vs python
- [ ] node → dev SSH (reverse direction) — currently only dev → node is wired
      (dev's pubkey on the boards). If a board ever needs to push files back to a
      workstation (e.g. uploading captures), set up an SSH server on the dev
      machine and install each node's public key there. Not needed yet.
- [ ] `tools/ssh/` + `tools/fleet/ssh.py` — host-key trust is TOFU
      (`StrictHostKeyChecking=accept-new`), so the first connection to a board is
      MITM-able. Consider host-key pinning: capture each board's host key during
      provisioning into a fleet `known_hosts` and switch to
      `StrictHostKeyChecking=yes` against it.
- [ ] `animon update <node-id>` — remote apt/pip upgrade as a fleet subcommand
      (folded into tools/fleet/ rather than a standalone maintenance script)
- [ ] `tools/fleet/deploy.py` — `deploy --dry-run` still makes one SSH call
      (`_remote_packages`) to compute packages-to-remove, so an offline dry-run
      (e.g. previewing a `--config` override) pauses on the connect timeout.
      Skip the remote query under `dry_run` and report removals as
      "unknown (offline)".

---

## Sensor Packages

- [x] `sensors/mq_array/` — MQ gas sensor array read over an MCU serial uplink
      (`AnalogArrayBase` + forge-built firmware)
- [x] `sensors/pressure_array/` (submodule) — logical surface across MCUs via the
      `mcu/circuit_python` family's `ads1115` module. Plus `sensors/analog_in`
      (heterogeneous scalars via `Ads1115Device`) and `sensors/board_temp` (sysfs).
- [ ] Promote in-tree sensors (`analog_in`, `board_temp`) to submodules if they
      grow independent lifecycles (convention: hardware sensors are submodules).
- [ ] `sensors/imu/` — IMU via RP2040/SAMD20 USB CDC (candidate `analog_array` /
      forge `mcu/rp2040/` consumer)
- [ ] `sensors/camera/` — Generalize `node/routers/camera.py` into a proper SensorBase plugin
- [~] Per-sensor `firmware/` subdirs — SUPERSEDED: firmware lives in `mcu/<family>/`
      (composed per instance by forge), not inside each sensor package.

---

## Infrastructure

- [x] Delete `LV-MaxSonar-EZ/` root directory — resolved
- [ ] Board profiles (`config/profiles/`) — hardware defaults per board type
- [ ] Fleet node discovery / health check endpoint
- [ ] Hotswap peripheral autodetection (scan I2C + USB on startup, auto-add to config)
- [x] `docs/architecture.md` — full system design, topology diagram, data flow
- [ ] `docs/tools/network.md` — embedded `tools/network/README.md` links to
      `ap.secrets.example` (a non-markdown asset), which 404s in the built site.
      Resolve alongside the AP-secrets cleanup (move the AP password out of the
      tracked `setup_ap.sh` into a gitignored secrets file).
- [ ] `docs/API.md` — complete endpoint reference (depends on API design above)
- [ ] `docs/boards/` — per-board wiring and setup guides
- [ ] Register `tools/usb/usbport/` as a git submodule
- [ ] Graft `LV-MaxSonar-EZ/` git history onto `sensors/lv_maxsonar` — directory is gone, can now proceed when desired

---

## Firmware (forge)

Implemented: forge core (validate/build/flash/clean), the AVR/Arduino target
(`analog_in`, `pwm_out`, `gpio_out`, `transport_serial`), compose + compile to a
real `.hex`, and the node-side `mq_array` sensor. Deferred, each reserved behind
an existing seam:

- [ ] Flash over SSH against live hardware — `ArduinoBuilder.deploy` is written
      (rsync `.hex` + `avrdude`) but unexercised without a board.
- [x] Command lane — end to end. MCU: `AC` command frames (`core/mcu_link.py`),
      `transport_serial.poll()` + generated `onCommand` dispatch. Node: the
      effector tier (below) owns the device link and sends commands.
- [x] Cortex runtime — devices (`core/device.py`: McuSerialDevice push,
      Ads1115Device pull), effectors (`core/effector_base.py`: PwmEffector request
      lane + StreamSink stream lane) driving through devices, policies + thalamic
      relay (`core/policy.py`, `core/relay.py`: always-on fan reflex), and the
      `mcu/circuit_python` forge family feeding `pressure_array`. See docs/cortex.md.
- [x] CircuitPython actuator path — `mcu/circuit_python` is now bidirectional:
      `pwm_out` module (`pwmio`, clean 25 kHz) + inbound `AC` command decode in the
      runtime. The chassis fans (4-pin PWM) live on the LXiao (XIAO RP2040,
      `config/mcus/lxiao.yaml`), driven by the node effector tier — moved off the
      AVR, whose timer map (Timer0 = millis) makes clean 25 kHz awkward.
- [ ] Real PWM frequency in the AVR `pwm_out` (lower priority now fans are on the
      RP2040) — it still ignores `freq_hz` and runs at `analogWrite`'s default.
      Only needed if an AVR ever drives a PWM load wanting >default frequency
      (timer config; keep off Timer0/D5/D6 which run `millis()`).
- [ ] Flash on real hardware — `ArduinoBuilder.deploy` (rsync .hex + avrdude over
      the host's SSH) is written but unexercised; needs avrdude on the host. Add a
      direct dev-machine-USB flash option for boards not behind a node.
- [ ] On-hardware command round-trip — verify node `send_command` → MCU
      `transport_serial.poll` → `onCommand` → `set_duty` on a real LArduino (the
      C++ RX parser only has the Python codec's round-trip behind it so far).
- [ ] Effector SBC-direct backend (`sbc_pwm`) for PWM on an SBC's own pins (the
      effector tier already dispatches on `backend`; add the backend).
- [ ] Stream-lane hardware effectors (speaker audio, addressable LED strip) — the
      lane + reference `StreamSink` exist; add real types.
- [ ] SPI transport — a `transport_spi` module + node-side reader; isolated to the
      transport module + `core/mcu_link.py` consumers.
- [ ] `mcu/circuit_python/` family — ONE generic CircuitPython runtime (code.py)
      shipped to any CP board (XIAO SAMD21, RP2040, …), parameterized by a forge-
      generated on-device config; builder "compiles" by copying files to CIRCUITPY.
      Organize firmware families by runtime/build method, not chip.
- [ ] Models tier (perception) — `accel.hailo` / `accel.coral` forge builders +
      a node-side Model interface that exposes learned features as relay signals
      (an "advanced sensor" policies observe). Plus an FPGA (`fpga.ice40`) builder.
- [ ] Learned/stochastic policies + on-device tuning/training (the `PolicyBase`
      `step(obs)→action` contract is the seam; today only `CurvePolicy`).
- [ ] Cross-node thalamic relay + declared reciprocal predict-down / error-up
      tracts between cortices (predictive coding); fleet aggregator nesting node
      trees by cortex. The local `core/relay.py` is the seam.
- [x] Channel-contract dedup — the MCU contract's `channels` is the single source;
      a device-fed sensor lists `devices: [<id>]` and `forge resolve <node>` derives
      its board-config `channels` (`tools/forge/resolve.py`). Author once.
- [ ] `animon`↔`forge` integration: `animon deploy` calls the resolver end-to-end
      and reconciles firmware as desired state (today `forge resolve` is a separate
      step; deploy doesn't run it yet).
- [ ] Protocol v2 — wider/float payloads; bump `VERSION` in `core/mcu_link.py` and
      the firmware `transport_serial` module together, branch decode on version.
- [ ] Generate the firmware serializer from `core/mcu_link.py` constants so the
      C++ and Python sides can't drift (today they mirror each other by hand).

## FPGA

- [ ] FPGA reconfiguration workflow via NeoCore2 + RP2040 power controllers
      (a forge `fpga.ice40` builder: HDL → yosys/nextpnr → bitstream → flash)
- [ ] SPI/I2S sensor data path from FPGA to host board
