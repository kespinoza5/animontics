# Animontics — Deferred Work

Items not yet implemented. Grouped by area.

---

## Embodiment Expansion

Auditory cortex, pressure lattice, servo proprioception, visceral sensing,
power-control brainstem. All software phases landed; design rationale lives
beside the code (module/sensor/effector READMEs, contract headers,
docs/cortex.md). What remains is bench bring-up + research tracks.

- [x] Phase 0 — config groundwork: `pizero_sonar` → `pizero_auditory`;
      node/board configs for `neocore2_hub` + `pizero_auditory`; QtPy RP2040
      placeholder on the orangepi configs
- [x] Phase 1 — forge: `mcu/circuit_python` modules `analog_in`, `servo_out`,
      `matrix_scan`, `scan_follower`; `feather_m4`/`qtpy_samd21`/`rp2040_zero`
      board profiles; contracts `featherm4_lattice`, `samd21_press0/1/2`
      (renamed from press0), `samd21_cervical`; CMD_SET_US/CMD_SET_GPIO
- [x] Phase 2 — `pressure_array` row-aligned sweep composition (row-tag
      channel 0, -1 sentinels, partial-sweep force emit); `web/shared/heatmap.js`
      extraction + lattice viewer
- [x] Phase 3 — `effectors/servo` (mcu + sbc_pwm backends) +
      `sensors/servo_feedback` (servo_pot calibration absorbs divider ratios)
- [x] Phase 4 — `sensors/current` + `sensors/radar_motion`;
      `effectors/power_rail` + gated≠failed (`GET /devices`, `power.<id>` relay
      signal); `policies/threshold` overcurrent guard; CP `gpio_out` module +
      `core/gpio.py` mcu backend; brainstem contracts `rp2040_power0/1`
- [x] Phase 5 — `devices/si5351` (clock-tree root, AN619 planner);
      `sensors/audio_in` (frame lane + level summaries); `effectors/speaker`
      (aplay stream + SD-pin gate)

### Bench backlog (hardware bring-up, in order)

- [ ] Lattice: flash featherm4_lattice + samd21_press0/1/2 (`forge build` →
      copy to CIRCUITPY); bench-test **CD4051 select/INH drive at 3.3 V**
      (VIH ≈ 3.5 V at 5 V mux supply — shift the 5 lines or swap the conductor
      to an RA4M1-Zero if lattice signal is weak); fill real
      `/dev/serial/by-id/` paths; `animon deploy neocore2_hub`; confirm
      84-channel sweeps in `web/viewers/pressure_array.html`
- [ ] Cervical: VERIFY A4/A5/A6 are pwmio-capable on the QtPy SAMD21 (now
      encoded in `mcu/circuit_python/boards/qtpy_samd21.yaml` with VERIFY marks —
      one `validate_pins.py` run on the QtPy confirms the whole table); fit
      **dividers on every pot tap** (DS3218 wiper swings to servo V+ 6–7.4 V);
      `set_us` round-trip → movement; calibrate `servo_pot` counts↔degrees
      endpoints; measure ACS712 `zero_counts` at rest
- [ ] Ears: dtoverlay pwm-2chan on GPIO12/13; ear ADS1115 at VDD=5 V behind
      the BSS138 shifter (5 V pull-ups on the ADS segment); calibrate ear
      feedback endpoints
- [ ] Power: wire the SRD-05VDC relay into the servo V+ rail (VERIFY
      active-low drive + the gpio line offset); overcurrent trip test under
      deliberate load; confirm members report `gated` in `GET /devices`;
      brainstem RP2040s: fill the GP-pin → power/reset wiring map in
      `config/mcus/rp2040_power0/1.yaml`, decide controller hosting
      (each can reset the other's host; neither strands the fleet)
- [ ] Audition: `tools/board/setup_i2s.sh` overlay on the pizero (PCM1808
      MASTER / Pi slave full-duplex — slave-mode PCM1808 needs SCKI synced to
      LRCK, which is why master mode is the plan); SI5351 readback on the
      3.3 V I2C segment; `arecord`/`aplay` sanity, then the sensor +
      effector lanes; set the MAX98357A gain strap conservatively (1 W driver)
- [ ] `larduino` MQ array unchanged but re-verify after hub re-cabling
- [ ] **LR4Z bring-up** (Waveshare RA4M1-Zero visceral front-end, `config/mcus/lr4z.yaml`):
      firmware is composed offline; hardware steps remain —
      (1) implement renesas **DFU flash** in `ArduinoBuilder` (board `flash.tool`
      override; the AVR path uses avrdude) — or flash via arduino-cli/IDE for now;
      (2) `forge build lr4z` on the toolchain (arduino-cli renesas core, WSL);
      (3) **VERIFY the pin map** in `mcu/arduino/boards/ra4m1_zero.yaml` against the
      Waveshare schematic (PWM-25 kHz / countio / Serial1 / ADC pads);
      (4) wire the 2N3904 inverter on the MB1010 TX → Serial1 (D0), AREF→5 V;
      (5) implement/verify **25 kHz** fan PWM (see Firmware) and calibrate the
      analog lanes (`acs712` zero/counts-per-amp, `maxsonar` `scale` mm/count) at
      10-bit + AREF=5 V — board values are placeholders;
      (6) fill real `/dev/serial/by-id/` for `lr4z`; `animon deploy neocore2_hub`;
      confirm both sonar lanes (`distance_mm` agree within near-field divergence),
      `rail_current.amps`, `fan_rpm`, fan `set_duty`, and relay on/off via
      `power_rail`.

### Research tracks / open seams

- [ ] CircuitPython `audiobusio.I2SIn` + clock-slave I2S TX (upstream
      contribution) → the Broca's-area QtPy RP2040 on the orangepi takes over
      the MAX98357A DIN (one wire + one effector backend change — the shared
      clock tree keeps it sample-coherent)
- [ ] rpi5 I2S tap onto the clock tree (4-pin connector already wired) — only
      if the network audio lane measures short; revisit with the FPGA fabric
- [ ] `fpga.ice40` forge builder (yosys/nextpnr/icepack) for the TinyFPGA BXs;
      reconfigurable 4-lane I2S/SPI fabric links; reflash via the brainstem
- [ ] Brainstem autonomy: watchdog firmware on the rp2040_power boards
      (deterministic, acts without a cortex) — today they are command-driven
- [x] forge: cross-contract validation for shared scan params — done (2026-06):
      `forge validate`/`build` check `rows` + `max_code` agree across every
      scan-module contract and that the conductor's `ack_pins` count matches
      the follower count (`tools/forge/cross_contract.py`). Assumes one sweep
      group fleet-wide; add a group key to the module params if a second
      lattice ever appears.
- [~] RA4M1-Zero swap points (boards ordered): lattice conductor (5 V mux
      drive + unshifted 5 V ADS I2C; cap DAC codes ≤3.3 V for the followers),
      visceral analog front-end (drops the shifted-I2C ADS1115), cervical
      (5 V servo logic). Forge approach DECIDED (2026-06): an **arduino-family
      Renesas board entry** — `mcu/arduino/boards/ra4m1_zero.yaml`
      (`arduino:renesas_uno:minima`). **CircuitPython is deprecated for this
      board**: the Waveshare RA4M1-Zero has no CP build, and CP would consume most
      of the flash even if it did. Visceral front-end COMPOSED (offline): the LR4Z
      (`config/mcus/lr4z.yaml`) carries the MB1010 sonar (analog AN + inverted-TX
      digital lanes), 3 fans + tach, ACS712, and the relay — replacing the
      SBC-side ADS1115 + lxiao + SBC-GPIO relay on `neocore2_hub`. Bench bring-up
      pending (below). Lattice-conductor + cervical RA4M1 swaps still open.
- [ ] Lattice inter-MCU coordination lane — DESIGN DECIDED (design-of-record):
      the RA4M1 conductor coordinates the SAMD21 followers over **analog
      DAC↔ADC point-to-point lines, NOT I2C**. Down: RA4M1 12-bit DAC broadcasts
      the active-row state (discrete bands, scaled ≤3.3 V so the non-5V-tolerant
      SAMD21s read it directly — doubles as free 5V→3.3V level translation,
      threshold-immune into the ADC). Up: each SAMD21's real 10-bit DAC returns a
      per-follower **salience/surprise magnitude** (clean — no PWM+RC smear; the
      SAMD21 DAC is why we don't need the RP2040's filtered-PWM workaround) into
      the RA4M1 A1/A2/A3. Rationale for not using I2C: a coordination round is
      ~µs and fully parallel on analog lines vs ~100s of µs–ms serialized on I2C,
      which is already saturated by the slow ADS1115 bulk reads (~860 SPS,
      ~18 ms/4-ADS-bus full scan). Analog also carries usable *coarse* timing
      (onset/dV/dt, cross-channel ordering at the ADC sample rate); digital
      spikes would buy sub-dwell event ordering but cost a 3.3→5V shifter
      (5 V RA4M1 VIH ≈ 3.5–4 V) — defer unless a reflex needs intra-dwell order.
      The returns are a low-latency *reflex hint* only: raw data still goes to
      the SBC over USB and Python owns the authoritative surprise (firmware moves
      bytes). I2C carries ADS bulk data only; 16 ADSs split 4-per-MCU is a
      perfect 0x48–0x4B address fit (no mux, no second bus). Open seam: the
      RA4M1 edge reflex that *consumes* the returns (re-scan/dwell on the salient
      row) — build only when one concrete reflex action is named; SBC pushes its
      params/thresholds down (predict-down), reflex emits its decision up. Wiring
      CONFIRMED (2026-06) on the Nano R4 + XIAO SAMD21: A0=P014_AN09_DAC (DAC
      out); Qwiic SCL/SDA = P400/P401 (IIC0) is a *separate* bus from A4/A5 =
      P100/P101, so the ADSs-on-Qwiic move genuinely frees A4/A5 as analog ins;
      XIAO SAMD21 fits the follower budget — A0 DAC return + 1 row-state ADC in +
      6 native ADC reads (internal mux, no follower CD4051) + D4/D5 I2C = 10 of
      11 pins. All lattice ADSs on the 3.3 V Qwiic rail → uniform
      front-end dividers + consistent calibration (keep this domain its own
      3.3 V island; don't mix with the 5 V ear-ADS segment).
- [ ] `animon status` device-tier surface: roll `GET /devices`
      (healthy/gated/down) into fleet status output

---

## API Design

The current sensor streaming API (`GET /sensors/{id}/stream`, `WS /sensors/{id}/ws`) is a starting point. Finalize with project team:

- [ ] Multiplexed stream endpoint (all sensors in one connection)?
- [ ] Command/control API (set VL53L1X ranging mode, etc.)?
- [ ] Node-to-node API for aggregator nodes pulling from sensor nodes?
- [ ] **Tiered authentication / access control** — deliberately deferred while the
      fleet lives on a trusted bench LAN, but it is the gate before any node binds
      beyond it. Design goal is *tiers*, not a single shared token: read-only
      telemetry (streams/status), actuation (effectors/policies), and admin
      (config/deploy) as separate credentials, so a dashboard can watch without
      being able to move the body. Credentials belong in the per-board gitignored
      `secrets.yaml` (see Infrastructure → peering projection) — note this secrets
      loading mechanism is documented in CLAUDE.md but not yet implemented in code.

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

- [x] Device/effector/policy board-config validation at deploy — done (2026-06):
      every device/effector/policy package declares `METADATA` in its `__init__.py`
      (description, required/optional config fields, backend kinds + required keys,
      known params — unified with the sensors pattern);
      `tools/fleet/validate_board.py` validates the board config against it
      (plus dangling backend.device / action.effector / sensor→device references and
      duplicate ids) and `animon deploy` aborts on errors before pushing. `animon
      types` lists the registered vocabulary. Also fixed en route: deploy now pushes
      the devices/effectors/policies plugin trees (it never did — fresh boards
      crashed on ImportError).
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
- [x] Bare-`pytest` collection hazard — resolved (2026-06): all interactive
      hardware bench scripts renamed `test_*` → `validate_*` (tf_mini,
      lv_maxsonar, mlx90640, vl53l1x, ir_xcvr). Bare `pytest -q` at the root
      now passes. Convention: pytest tests are `test_*.py`; on-hardware bench
      scripts are `validate_*.py`.
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
- [ ] Test coverage — areas deferred after the 2026-06 shoring pass (which added
      tests for reconcile, core/config, broadcaster, registry, the fleet SSH
      transport, and the node app + routers): sensor read loops
      (tf_mini/vl53l1x/… via a fake-driver harness), `tools/fleet/`
      deploy.py / sync.py / probe.py orchestration (needs an SSH fake at the
      run_remote seam), and the CLI entry points (`animon.py`, `forge.py`).
- [ ] `animon update <node-id>` — remote apt/pip upgrade as a fleet subcommand
      (folded into tools/fleet/ rather than a standalone maintenance script)
- [x] `tools/fleet/deploy.py` — `deploy --dry-run` is now fully offline: the
      `_remote_packages` SSH query is skipped under dry_run and removals report
      as "unknown (dry-run skips the board query)". (2026-06)

---

## Sensor Packages

- [x] `sensors/mq_array/` — MQ gas sensor array read over an MCU serial uplink
      (`AnalogArrayBase` + forge-built firmware)
- [x] `sensors/pressure_array/` — logical surface across MCUs via the
      `mcu/circuit_python` family's `ads1115` module. Plus `sensors/analog_in`
      (heterogeneous scalars via `Ads1115Device`) and `sensors/board_temp` (sysfs).
- [x] `sensors/sara_r5_gnss` + `sensors/sara_r5_lte` — GNSS + LTE-M from the
      u-blox SARA-R5 modem (UART), two logical sensors over one `devices/sara_r5`
      device. Plus `sensors/ozzmaker_10dof` — LSM6DSL + MMC5983MA + BMP388 over I2C.
- [~] Promote in-tree sensors to submodules — SUPERSEDED (2026-06): the
      submodule convention is retired. All seven sensor submodules were folded
      into the monorepo via `git subtree` (history preserved); every sensor is
      now a plain directory. A package would only be split out again (with a
      real remote) if it gained an external consumer or release cycle.
- [ ] `sensors/sara_r5_gnss` + `sensors/sara_r5_lte` are two views of ONE physical
      board on ONE UART (unified at the `sara_r5` device). They're separate packages
      only because `load_all_metadata` binds one METADATA per package. If the fleet
      model ever supports a multi-type package, consider folding them into one.
- [ ] `sensors/ozzmaker_10dof/driver_bmp388.py` — the BMP388 pressure compensation
      is validated only against synthetic calibration data (the temp path is right;
      pressure produces non-representative values with fake NVM coefficients). Verify
      Pa output against a reference barometer on first boot with real chip cal data.
- [ ] `sensors/sara_r5_gnss` — wire the SARA-R5 TP (time-pulse / PPS) pin as a GPIO
      interrupt for 1 Hz timing sync. Routed to the SBC and documented, not yet
      implemented (deferred per the build plan).
- [ ] `sensors/imu/` — IMU via RP2040/SAMD20 USB CDC (candidate `analog_array` /
      forge `mcu/rp2040/` consumer)
- [ ] `sensors/camera/` — Generalize `node/routers/camera.py` into a proper SensorBase plugin
- [~] Per-sensor `firmware/` subdirs — SUPERSEDED: firmware lives in `mcu/<family>/`
      (composed per instance by forge), not inside each sensor package.

---

## Infrastructure

- [x] `README.md` — CI/Docs badges point at
      `https://github.com/kespinoza5/animontics/actions/...` (resolved 2026-08-05).
- [x] `.github/workflows/docs.yml` — Pages enabled with source "GitHub Actions";
      site live at https://kespinoza5.github.io/animontics/ (2026-08-05).
- [x] Delete `LV-MaxSonar-EZ/` root directory — resolved
- [ ] `core/gpio.py` — VERIFY the SARA-R5 power/reset GPIO on the Orange Pi
      Zero 2 with `gpioinfo`/`gpiofind`, and the installed gpiod binding major
      (v1 vs v2). The PI6=262/PI16=272 bank arithmetic now lives in
      `config/profiles/orangepi_zero2.yaml` (the authoritative home, marked
      VERIFY) and deploy checks line specs against it. `LibgpiodOutputLine` is
      written but unexercised on hardware.
- [x] `core/gpio.py` — `mcu` backend implemented (2026-06): `McuOutputLine` drives
      a pin through a device's command sink via `CMD_SET_GPIO` (Phase 4). The
      `power_rail` effector uses it (`backend: {kind: mcu, device, channel,
      active_low}`) — e.g. the LR4Z relay and the brainstem RP2040s.
- [x] `config/nodes/*.yaml` gitignore vs docs reconciled — CLAUDE.md, architecture.md,
      CONTRIBUTING, and the example headers now all state config/nodes is gitignored
      (only `example.yaml` tracked), matching `.gitignore`. The `proprioception` node
      lives on disk only, as intended.
- [x] Node address authority — `hostname` + HTTP `port` moved from `config/nodes/`
      (desired state) into `config/animon.yaml` (access). `config/nodes/` is now pure
      desired state; the board `network` block is the node's serving config, projected
      from the access `port` by reconcile; `python -m node` binds from it. One source.
- [ ] API auth before the served port is exposed beyond a trusted network — the node
      HTTP API is currently unauthenticated, so anyone who can reach `host:port` can
      read sensors / drive effectors. Prerequisite for binding to a non-loopback
      interface on an untrusted network. Acknowledged and deferred (2026-06): we are
      bench-only on a trusted LAN; the design target is tiered credentials — see
      API Design → tiered authentication.
- [ ] Peering projection — when the cross-node relay tracts land, the node serving
      config grows a `peers:` section projected from the fleet topology
      (`config/animon.yaml`); inter-node auth credentials come from a gitignored
      per-board `secrets.yaml`, never from `animon.yaml` or the board config. Keep
      address (topology) and identity (credential) in separate places.
- [x] Board profiles (`config/profiles/`) — landed (2026-06) as **SBC
      pin-capability profiles** per node_type (tracked): gpiochip + header line
      offsets, pwm chips + required overlays, role-bound bus pins; deploy
      validates line specs and sbc_pwm backends against them. Extend the same
      files if per-board-type *defaults* are ever needed.
- [ ] Fleet node discovery / health check endpoint
- [ ] Hotswap peripheral autodetection (scan I2C + USB on startup, auto-add to config)
- [x] `docs/architecture.md` — full system design, topology diagram, data flow
- [ ] `docs/tools/network.md` — embedded `tools/network/README.md` links to
      `ap.secrets.example` (a non-markdown asset), which 404s in the built site.
      Resolve alongside the AP-secrets cleanup (move the AP password out of the
      tracked `setup_ap.sh` into a gitignored secrets file).
- [ ] `docs/API.md` — complete endpoint reference (depends on API design above)
- [ ] `docs/boards/` — per-board wiring and setup guides
- [~] Register `tools/usb/usbport/` as a git submodule — SUPERSEDED (2026-06):
      submodule convention retired; it stays a plain tracked directory.
- [ ] Graft `LV-MaxSonar-EZ/` git history into the monorepo's `sensors/lv_maxsonar`
      path (subtree merge of the old standalone repo) — can proceed when desired

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
      runtime. The chassis fans (4-pin PWM) were initially moved off the AVR
      (Timer0/millis conflict) onto a CP board; on `neocore2_hub` they were later
      consolidated onto the LR4Z (Renesas RA4M1, `config/mcus/lr4z.yaml`).
- [ ] Real PWM frequency in `pwm_out` — it still ignores `freq_hz` and runs at
      `analogWrite`'s default. **Now needed**: the LR4Z (RA4M1) drives 4-pin
      chassis fans that want clean **25 kHz**. Implement the renesas GPT/
      `analogWriteFrequency` path (verify the core API on hardware — it's why this
      is deferred). AVR side stays optional (keep off Timer0/D5/D6 which run
      `millis()`).
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
- [x] `animon`↔`forge` integration — done (2026-06): `animon deploy` runs the
      channel resolver itself (`resolve_node_config`; shipped configs always carry
      contract-derived channels, explicit channels win, a channel-less contract is
      flagged with the `forge channels` fix), and firmware build-state drift
      (`tools/forge/drift.py`: unbuilt / stale-vs-contract per declared usb_mcu)
      surfaces in `status`, `diff`, and as deploy warnings. Deploy still never
      builds/flashes — that stays a forge step because it needs the hardware.
- [ ] forge: manifest-level `valid:` for module config values — the CP
      `ads1115` module's `chips: [{addr, gain}]` accept any addr/gain today;
      a manifest schema for nested config (like the board-config `valid:`)
      would close the same gap one layer down. Path expressions needed for
      list-of-dict params; deferred until a second case appears.
- [ ] `sensors/ir_xcvr` — declare its LIRC dependency as a bus/overlay
      requirement (gpio-ir / gpio-ir-tx overlays + the rx/tx GPIO choices)
      once a profile section shape for IR is settled; today only the lirc
      device paths are configured.
- [ ] `animon probe` live pin/overlay verification — read `/sys/class/pwm`,
      `/proc/device-tree`, and `gpioinfo` over SSH to confirm what the offline
      profile checks can't: overlays actually enabled, gpiochip names/line
      counts as profiled. The seam is noted in config/profiles/README.
- [ ] RP2040 PWM slice arithmetic — two pins on one PWM slice must share a
      frequency; the capability table can't express it. Needs a per-chip rule
      in the claims checker if a contract ever drives two different
      frequencies on adjacent pins.
- [ ] Voltage-domain checks — board files and SBC profiles carry `logic_v`;
      a future check could flag a 3.3 V driver claiming a module whose
      manifest declares a higher required VIH (the CD4051 lattice concern).
      Data is in place; the check is not.
- [ ] Protocol v2 — wider/float payloads; bump `VERSION` in `core/mcu_link.py` and
      the firmware `transport_serial` module together, branch decode on version.
- [ ] Generate the firmware serializer from `core/mcu_link.py` constants so the
      C++ and Python sides can't drift (today they mirror each other by hand).

## FPGA

- [ ] FPGA reconfiguration workflow via NeoCore2 + RP2040 power controllers
      (a forge `fpga.ice40` builder: HDL → yosys/nextpnr → bitstream → flash)
- [ ] SPI/I2S sensor data path from FPGA to host board
