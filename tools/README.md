# Tools

Board management and provisioning scripts. Each subdirectory does one thing.

## Fleet Management — `fleet/`

The primary deployment tool. The `animon` CLI reads `config/animon.yaml` and
keeps every board's software and config in sync with the desired fleet state.

```bash
# From the project root
python -m tools.fleet.animon status          # check all nodes
python -m tools.fleet.animon deploy my_rpi_node
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
| `maintenance/deploy.sh` | Legacy shell-based deploy (superseded by `fleet/`) |

---

## Pre-flight checklist before first deploy

1. SSH key auth configured: `ssh-copy-id pi@<board-ip>`
2. SSH agent running: `eval $(ssh-agent) && ssh-add`
3. Board reachable: `tools/board/verify_comms.sh` (run on the board itself)
4. Node listed in `config/animon.yaml`

```bash
# Quick connectivity check from dev machine
ssh pi@192.168.1.x echo OK
```
