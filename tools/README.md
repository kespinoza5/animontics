# Tools

Board management and provisioning scripts. Each subdirectory does one thing.

## Fleet Management — `fleet/`

The primary deployment tool. The `animon` CLI reads `config/animon.yaml` and
keeps every board's software and config in sync with the desired fleet state.

```bash
# From the project root
python -m tools.fleet.animon status          # check all nodes
python -m tools.fleet.animon deploy my_sbc_node
python -m tools.fleet.animon diff  my_sbc_node
```

See [`fleet/README.md`](fleet/README.md) for full documentation.

---

## Other Tools

| Tool | Purpose |
|------|---------|
| `fleet/` | Full fleet management CLI (deploy, status, diff, pull, probe, revert) |
| `board/verify_comms.sh` | Scan I2C buses, list UART and USB serial devices |
| `board/setup_i2c.sh` · `setup_uart.sh` · `setup_spi.sh` · `setup_i2s.sh` | Enable a hardware bus on the board (run as root; reboot required) |
| `ssh/fleet_access.sh` | One-command access setup/refresh/rotate — wraps the scripts below |
| `ssh/gen_keys.sh` | Generate an Ed25519 key pair for fleet access |
| `ssh/distribute_keys.sh` | Push the fleet public key to every node in `animon.yaml`; `--harden`/`--unharden` toggle board password auth |
| `ssh/setup_ssh_config.sh` | Write `~/.ssh/config` aliases so `ssh`/`scp <node-id>` work with no `-i` and no `ssh-add` |
| `ssh/revoke_keys.sh` | Remove a fleet public key from the boards (rotation / revocation) |
| `network/setup_ap.sh` | Configure node as a WiFi access point |
| `network/undo_ap.sh` | Revert AP configuration |
| `usb/usbport/` | Manage USB ethernet gadget interfaces (standalone binary) |
| `dev/audit.py` | Audit sensor packages against the plugin contract |

Where a script runs matters: `board/` scripts run **on the board** (the setup
ones need root), `ssh/` scripts run **on your dev machine**, and `fleet/` drives
everything remotely. See [`board/README.md`](board/README.md) and
[`ssh/README.md`](ssh/README.md) for details.

---

## Bootstrapping a new board

A board does **not** need an entry in `config/animon.yaml` to receive its first
deploy. As long as the node's desired state exists in `config/nodes/<id>.yaml`,
point `animon` at the board's address directly:

```bash
# First deploy to a board not yet in animon.yaml
python -m tools.fleet.animon deploy <node-id> --host <board-ip> --user pi
```

This runs the full reconcile + METADATA-validate + health-check flow — it is not
a degraded path. Once the board is up, record its access details in
`config/animon.yaml` so subsequent `deploy` / `status` / `diff` work by node-id
alone. (This replaces the old `maintenance/deploy.sh` shell script.)

---

## Pre-flight checklist before first deploy

1. SSH access set up: `tools/ssh/fleet_access.sh setup` (generates the fleet key,
   pushes it to every board, and writes `~/.ssh/config` aliases). This rolls up
   `gen_keys.sh` + `distribute_keys.sh` + `setup_ssh_config.sh`.
2. No SSH agent needed — `setup_ssh_config.sh` pins the key via `IdentityFile`.
   (If you skip it, run `ssh-add ~/.ssh/animontics_ed25519` instead.)
3. Hardware buses enabled on the board: `tools/board/setup_i2c.sh` /
   `setup_uart.sh` / `setup_spi.sh` as needed (run on the board, then reboot)
4. Board reachable: `tools/board/verify_comms.sh` (run on the board itself)
5. Node desired state in `config/nodes/<id>.yaml` (access in `config/animon.yaml`,
   or pass `--host` to bootstrap)

```bash
# Quick connectivity check from dev machine
ssh pi@<board-ip> echo OK
```
