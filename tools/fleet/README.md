# tools/fleet — Fleet Management CLI

The `animon` CLI synchronises the distributed sensor network defined in
`config/animon.yaml` with the live state of every board.  It is the primary
deployment tool for animontics — boards are never set up by manually cloning
the repo.

---

## Quick reference

```
animon deploy  <node-id>  [--dry-run] [--user USER] [--verbose]
animon status  [<node-id>] [--json]
animon diff    <node-id>  [--user USER] [--verbose]
animon pull    <node-id>  [--user USER] [--dry-run]
animon probe   <node-id>  [--user USER]
```

All commands accept `--config PATH` to point at a non-default `animon.yaml`.

---

## Commands

### `deploy`

Push the desired state described in `animon.yaml` to a single board.

**What it does:**

1. Loads the node's desired sensor list from `animon.yaml`.
2. SSHes to the board and reads the current `config.yaml` (port / bus / baud wiring).
3. **Reconciles** the two:
   - Sensors in both → keep existing wiring unchanged.
   - Sensors in `animon.yaml` but not on the board → add with defaults from sensor `METADATA`.
   - Sensors on the board but removed from `animon.yaml` → mark `enabled: false`.
4. Validates all enabled sensors against `METADATA` constraints (baud rate, I2C address, etc.).
5. Rsyncs `core/`, `node/`, and the needed sensor packages.  Removes packages no longer needed.
6. Writes the new `config.yaml` to the board.
7. Runs `pip3 install -r requirements.txt` and restarts the `animontics-node` systemd service.
8. Polls `GET /` until the node reports healthy (up to 10 attempts × 2 s).

```bash
# Show what would change — no files transferred
animon deploy my_sbc_node --dry-run

# Deploy for real, showing detailed rsync output
animon deploy my_rpi_node --verbose

# Deploy as a different SSH user
animon deploy pi_zero_sonar --user ubuntu
```

**Exit codes:** `0` = success, `1` = error.

---

### `status`

Compare `animon.yaml` desired state against every node's live state.

Queries `GET /config` on each node.  Nodes that do not respond via HTTP are
marked *unreachable*.

```bash
animon status                    # all nodes
animon status my_rpi_node          # one node
animon status --json             # machine-readable JSON
```

**Exit codes:** `0` = all in-sync, `1` = error, `2` = drift detected.

---

### `diff`

Show what `deploy` would change for a node **without applying anything**.

Fetches the board's current config via HTTP first; falls back to SSH if the
node is not running the animontics service yet (e.g. fresh install).

```bash
animon diff my_sbc_node
```

**Exit codes:** `0` = no changes, `1` = error, `2` = changes pending.

---

### `pull`

Read a board's live sensor config and merge new sensors into `animon.yaml`.

Useful after directly editing a board's `config.yaml` — brings the fleet
record up to date without a full deploy cycle.  Only *adds* sensors to
`animon.yaml`; never removes.

```bash
animon pull pi_zero_sonar --dry-run   # preview additions
animon pull pi_zero_sonar             # write animon.yaml
```

**Exit codes:** `0` = success (nothing to pull is also 0), `1` = error.

---

### `probe`

SSH into a board and detect connected hardware.

Scans I2C buses (`i2cdetect`), UART devices (`/dev/ttyAMA*`), and USB CDC
devices (`/dev/ttyACM*`, `/dev/ttyUSB*`).  Matches findings against sensor
`METADATA` and reports probable sensor types, connection parameters, and
whether each is already in `animon.yaml`.

```bash
animon probe my_sbc_node
```

Example output:

```
Probe report: my_sbc_node
──────────────────────────────────────────────────
Detected hardware:
  I2C /dev/i2c-3: 0x29, 0x33
  UART: /dev/ttyAMA0
  USB CDC: none found

Sensor matches:
  [HIGH  ] vl53l1x              bus=3 addr=0x29 ✓
           I2C bus 3 address 0x29 matches VL53L1X Time-of-Flight default address
  [HIGH  ] mlx90640             bus=3 addr=0x33 ✓
           I2C bus 3 address 0x33 matches MLX90640 Thermal Camera default address
  [MEDIUM] tf_mini              port=/dev/ttyAMA0 baud=115200 (not in animon.yaml)
           UART device /dev/ttyAMA0 could be Benewake TF Mini Plus LiDAR — verify wiring
```

**Exit codes:** `0` = completed, `1` = error.

---

## How it works — the three-layer config

| Layer | File | Owner | Contains |
|-------|------|-------|----------|
| Fleet desired state | `config/animon.yaml` | Repo | Which sensors each node *should* have |
| Board wiring reality | `<deploy_path>/config/config.yaml` | Board | Port, bus, baud, address for each sensor |
| Hardware constraints | `sensors/<type>/__init__.py` `METADATA` | Repo | Valid connection types, addresses, baud rates |

`deploy` negotiates between all three layers.  Neither the fleet config nor
the board config is blindly overwritten — the reconciler merges them
intelligently, and the board's physical wiring decisions are always preserved.

---

## Running the CLI

From the project root:

```bash
# As a module
python -m tools.fleet.animon deploy my_sbc_node

# Or add an alias to your shell profile
alias animon="python -m tools.fleet.animon"
animon status
```

---

## SSH prerequisites

- SSH key pair set up with `ssh-copy-id user@board` (or equivalent).
- SSH agent running with the key loaded (`ssh-add`).
- No passwords — the tool uses `BatchMode=yes` and will fail fast if key auth
  is not configured.

See `tools/board/verify_comms.sh` for a pre-flight connectivity check.

---

## Module structure

| File | Purpose |
|------|---------|
| `animon.py` | CLI entry point — argparse dispatch |
| `deploy.py` | `deploy()` — full deploy flow |
| `sync.py` | `status()`, `diff()`, `pull()` |
| `probe.py` | Hardware detection and sensor matching |
| `reconcile.py` | Config negotiation logic; `METADATA` loader |
| `ssh.py` | SSH/rsync transport (wraps system `ssh`/`rsync`) |
