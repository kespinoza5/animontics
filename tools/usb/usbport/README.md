# usbport

A command-line tool for managing USB ethernet interfaces on Linux SBCs (Orange Pi, Raspberry Pi, etc.). Designed for setups where a USB-A port is shared between USB ethernet gadgets (Pi Zero 2W, Coral Dev Board, etc.) and HID devices like mice and keyboards.

Profiles are keyed to the **physical USB port** rather than the device MAC address, so they survive device reboots and MAC changes.

## Requirements

- Python 3.8+
- NetworkManager (`nmcli`)

## Install

```bash
chmod +x usbport
sudo cp usbport /usr/local/bin/usbport
```

## Usage

```
usbport                              show status of all detected USB ethernet interfaces
usbport net [--ip x] [--port x]     bring up a USB ethernet interface with a static IP
usbport device [--port x]            bring down a USB ethernet interface
usbport status [--port x]            show detailed status
usbport profiles                     list all usbport NetworkManager profiles
usbport show <port>                  show full NM profile details for a port
usbport clean                        delete all usbport NM profiles
```

## Examples

### Single device (auto-detected)

```bash
sudo usbport net                     # bring up, default IP 192.168.8.1
sudo usbport net --ip 192.168.8.5   # bring up with a custom IP
sudo usbport device                  # bring down, port ready for a mouse/keyboard
sudo usbport                         # quick status
```

### Multiple devices

When multiple USB ethernet devices are plugged in, use `--port` to target a specific one.
Run `usbport` first to see which ports are in use:

```
found 2 USB ethernet interface(s):
  port 1-1  iface: enx9e10d8f2a40c  state: 100 (connected)  ip: 192.168.8.1/24  (profile exists)
  port 1-2  iface: enx82bb47745333  state: 30 (disconnected)  ip: none  (no profile)
```

Then target by port:

```bash
sudo usbport net --ip 192.168.8.1 --port 1-1
sudo usbport net --ip 192.168.8.5 --port 1-2
sudo usbport device --port 1-1
sudo usbport show 1-1
```

### Profile management

```bash
sudo usbport profiles    # list all usbport-* NM profiles
sudo usbport show 1-1    # inspect the profile for port 1-1
sudo usbport clean       # delete all usbport profiles
```

## How it works

USB ethernet gadgets (devices running `g_ether`, `cdc_ether`, or RNDIS) enumerate on the host as a `cdc_ether` network interface. Linux assigns these a MAC-derived name like `enx9e10d8f2a40c` which can change between reboots of the connected device.

`usbport` detects these interfaces by their kernel driver (`cdc_ether`) and maps them to their stable physical USB port path (e.g. `1-1`, `1-2`). NetworkManager connection profiles are named `usbport-<port>` (e.g. `usbport-1-1`) so the same profile is reused regardless of MAC or interface name changes.

## Notes

- Requires `sudo` for NM profile creation and interface management
- `usbport device` only brings the connection down — the port remains powered, so HID devices work without any additional steps
- If a connected device has a changing MAC address, you can stabilize it on the device side (e.g. set a fixed `host_addr` in `g_ether` via `/boot/cmdline.txt` on a Pi)
- Works on any board with NetworkManager; port ids will reflect the host board's USB topology
