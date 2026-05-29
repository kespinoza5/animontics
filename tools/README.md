# Tools

Board management and provisioning scripts. Each subdirectory does one thing.

## Deployment Guide — What to install on each board type

| Board | Tools needed |
|-------|-------------|
| All Linux boards | `maintenance/deploy.sh`, `board/verify_comms.sh` |
| WiFi AP nodes | `network/setup_ap.sh`, `network/undo_ap.sh` |
| USB hub hosts (NeoCore2) | `usb/usbport/` |
| Boards receiving USB gadget devices | `usb/usbport/` |

## Tools

| Tool | Purpose |
|------|---------|
| `usb/usbport/` | Manage USB ethernet gadget interfaces (standalone binary) |
| `network/setup_ap.sh` | Configure node as a WiFi access point |
| `network/undo_ap.sh` | Revert AP configuration |
| `board/verify_comms.sh` | Scan I2C buses, list UART and USB serial devices |
| `maintenance/deploy.sh` | Deploy animontics to a board via SSH + rsync |

## Deploying a Tool to a Board

```bash
# Copy a tool to a board and make it executable
scp tools/board/verify_comms.sh pi@192.168.1.x:/tmp/
ssh pi@192.168.1.x 'chmod +x /tmp/verify_comms.sh && /tmp/verify_comms.sh'

# Or via deploy.sh which handles the full animontics deployment
./tools/maintenance/deploy.sh pi@192.168.1.x
```
