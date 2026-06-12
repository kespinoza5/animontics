# tools/fleet — Fleet Management CLI

The `animon` CLI keeps every board's software and config in sync with the
desired fleet state.  It is the primary deployment tool — boards are never
set up by manually cloning the repo onto each one.

---

## Quick reference

```
animon deploy  <node-id>  [--dry-run] [--user USER] [--host IP] [--deploy-path PATH]
                          [--config PATH] [--note TEXT] [--yes] [--verbose]
animon revert  <node-id>  [--user USER] [--host IP] [--dry-run] [--verbose]
animon status  [<node-id>] [--json]
animon diff    <node-id>  [--user USER] [--verbose]
animon pull    <node-id>  [--user USER] [--dry-run]
animon probe   <node-id>  [--user USER]
animon types
```

`deploy` validates the whole board config before pushing anything: sensors
against their `METADATA` constraints, and the **devices/effectors/policies
tiers against each type's `SPEC`** (`tools/fleet/validate_board.py`) — unknown
kinds, missing required fields, a `backend.device` or `action.effector` that
names nothing on the board, and dangling sensor→device references all fail on
the dev machine with the file to fix. Unknown `params:` keys print as warnings.
`animon types` lists every registered sensor/device/effector/policy type with
its one-line description — the authoring vocabulary.

Global flags:

```
--access PATH   Path to animon.yaml access config   (default: config/animon.yaml)
--nodes DIR     Path to nodes/ desired-state dir    (default: config/nodes/)
```

---

## Four-layer config model

`animon` negotiates four config layers on every operation:

| Layer | File | In repo? | Contains |
|-------|------|----------|----------|
| **Desired state** | `config/nodes/<id>.yaml` | ✅ | Which sensors each node should run (id + type only), capabilities, role |
| **Fleet access** | `config/animon.yaml` | ❌ | IPs, SSH users — how to reach each board |
| **Board wiring** | `config/boards/<id>.yaml` + board's `config.yaml` | ❌ | Physical connections: port, bus, baud, address |
| **Hardware constraints** | `sensors/<type>/__init__.py` METADATA | ✅ | Valid connection types, locked baud rates, I2C address ranges |

Neither the desired-state file nor the board's wiring config is blindly
overwritten.  The reconciler merges them: existing wiring is preserved,
new sensors are bootstrapped from METADATA defaults, removed sensors are
disabled.

---

## Commands

### `deploy`

Push the desired state from `config/nodes/<id>.yaml` to a single board.

**What it does:**

1. Load `config/nodes/<id>.yaml` — desired sensors for this node.
2. Load `config/animon.yaml` — SSH credentials and IP.
3. Read `config/boards/<id>.yaml` staging copy (or SSH for live config).
4. **Reconcile**: keep existing wiring, add new sensors from METADATA defaults,
   disable sensors removed from desired state.
5. Validate all enabled sensors against METADATA constraints.
6. Rsync `core/`, `node/`, and only the needed sensor packages.
   Remove packages no longer needed.
7. Write the new `config.yaml` to the board.
8. Run `pip3 install -r requirements.txt` and restart `animontics-node`.
9. Poll `GET /` until the node reports healthy (up to 10 attempts × 2 s).
10. Update `config/boards/<id>.yaml` staging copy.

```bash
animon deploy my_sbc_node             # deploy
animon deploy my_sbc_node --dry-run   # show what would change — no files transferred
animon deploy my_sbc_node --verbose   # show detailed rsync progress
animon deploy my_sbc_node --user pi   # override SSH user
```

**Bootstrap a board not yet in `animon.yaml`:** the desired state in
`config/nodes/<id>.yaml` is enough — point `deploy` at the board's address
directly. The full reconcile + validate + health-check flow still runs.

```bash
animon deploy my_sbc_node --host 192.168.1.50 --user pi
# then record the board in config/animon.yaml so node-id alone works afterward
```

**Override deploy (testing / debugging / rollback):** push a pre-built
`config.yaml` *verbatim* with `--config`. It is validated against METADATA but
**not** reconciled, and the staged baseline (`config/boards/<id>.yaml`) is left
untouched. Instead an override marker (`config/boards/<id>.override.yaml`) is
written so the deviation shows up in `status`/`diff` and can be undone exactly.

```bash
animon deploy my_sbc_node --config experiments/lidar_230k.yaml \
                          --note "test tf_mini @ 230400"
```

A plain `deploy` onto a board that has an active override prompts before
discarding it (`--yes` to skip the prompt). Use `revert` to restore the
baseline explicitly.

**Exit codes:** `0` = success, `1` = error.

---

### `revert`

Discard a board's active override and restore the staged baseline. Reconciles
from `config/nodes/` + `config/boards/<id>.yaml` (the baseline the override
never touched), redeploys, and deletes the override marker. A no-op if the node
has no active override.

```bash
animon revert my_sbc_node
animon revert my_sbc_node --dry-run   # show what reverting would change
```

**Exit codes:** `0` = success (nothing to revert is also 0), `1` = error.

---

### `status`

Compare desired state (`config/nodes/`) against every board's live state.

Queries `GET /config` on each node.  Nodes that do not respond via HTTP are
marked *unreachable*. A board running an ad-hoc override (see `deploy --config`)
is shown as `OVERRIDE` with its note — a tracked, intentional deviation, kept
visually distinct from accidental `DRIFTED`.

```bash
animon status                      # all nodes
animon status my_sbc_node          # one node
animon status --json               # machine-readable JSON
```

**Exit codes:** `0` = all in-sync, `1` = error, `2` = drift *or* an active
override detected (the board is not on its staged baseline).

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

Fetch a board's live `config.yaml` and update two local files:

- `config/boards/<id>.yaml` — full wiring staging copy (always updated)
- `config/nodes/<id>.yaml` — adds any sensor `{id, type}` pairs enabled on the
  board but not yet in desired state

Never removes sensors from desired state.  Useful after manually editing a
board's `config.yaml` directly — brings local staging and desired state up
to date without a full deploy cycle.

```bash
animon pull my_sbc_node --dry-run   # preview additions
animon pull my_sbc_node             # write both files
```

**Exit codes:** `0` = success (nothing to pull is also 0), `1` = error.

---

### `probe`

SSH into a board and detect connected hardware.

Scans I2C buses (`i2cdetect`), UART devices (`/dev/ttyAMA*`), LIRC IR devices,
and USB CDC devices (`/dev/ttyACM*`, `/dev/ttyUSB*`).  Matches findings against
sensor METADATA and reports probable sensor types, connection parameters, and
whether each matches the node's desired state.

```bash
animon probe my_sbc_node
```

Example output:

```
Probe report: my_sbc_node
──────────────────────────────────────────────────
Detected hardware:
  I2C /dev/i2c-1: 0x29, 0x33
  UART: /dev/ttyAMA0
  USB CDC: none found
  LIRC: none found

Sensor matches:
  [HIGH  ] vl53l1x              bus=1 addr=0x29 ✓
           I2C bus 1 address 0x29 matches VL53L1X Time-of-Flight default address
  [HIGH  ] mlx90640             bus=1 addr=0x33 ✓
           I2C bus 1 address 0x33 matches MLX90640 Thermal Camera default address
  [MEDIUM] tf_mini              port=/dev/ttyAMA0 baud=115200 (not in desired state)
           UART device /dev/ttyAMA0 could be Benewake TF Mini Plus LiDAR — verify wiring
```

**Exit codes:** `0` = completed, `1` = error.

---

## Running the CLI

From the project root:

```bash
# As a module (always works)
python -m tools.fleet.animon deploy my_sbc_node

# Or add a shell alias
alias animon="python -m tools.fleet.animon"
animon status
```

---

## SSH prerequisites

- SSH key pair set up: `ssh-copy-id user@<board-ip>` (or equivalent).
- SSH agent running with the key loaded: `ssh-add`.
- No passwords — the tool uses `BatchMode=yes` and fails fast if key auth
  is not configured.
- `rsync` available on the dev machine.

---

## Module structure

| File | Purpose |
|------|---------|
| `animon.py` | CLI entry point — argparse, subcommand dispatch |
| `deploy.py` | `deploy()` — full deploy flow |
| `sync.py` | `status()`, `diff()`, `pull()` |
| `probe.py` | Hardware detection and sensor-type matching |
| `reconcile.py` | Config negotiation logic; METADATA loader |
| `ssh.py` | SSH/rsync transport (wraps system `ssh`/`rsync`) |
