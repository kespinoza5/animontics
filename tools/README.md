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
| `fleet/` | Full fleet management CLI (deploy, status, diff, pull, probe) |
| `board/verify_comms.sh` | Scan I2C buses, list UART and USB serial devices |
| `network/setup_ap.sh` | Configure node as a WiFi access point |
| `network/undo_ap.sh` | Revert AP configuration |
| `usb/usbport/` | Manage USB ethernet gadget interfaces (standalone binary) |
| `dev/audit.py` | Audit sensor packages against the plugin contract |

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

1. SSH key auth configured: `ssh-copy-id pi@<board-ip>`
2. SSH agent running: `eval $(ssh-agent) && ssh-add`
3. Board reachable: `tools/board/verify_comms.sh` (run on the board itself)
4. Node desired state in `config/nodes/<id>.yaml` (access in `config/animon.yaml`,
   or pass `--host` to bootstrap)

```bash
# Quick connectivity check from dev machine
ssh pi@<board-ip> echo OK
```
