# tools/usb

Tools for managing USB connections between boards.

## Tools

### [`usbport/`](usbport/README.md)

Standalone binary tool for managing USB ethernet gadget network interfaces. Used when a board (e.g. Pi Zero 2W) connects to a host board (e.g. OrangePi) over USB in gadget mode — `usbport` configures and names the resulting network interface so the host can reach the gadget over a stable address.

See [usbport/README.md](usbport/README.md) for full usage.

## USB Gadget Network Overview

```
Pi Zero 2W ──USB gadget──► OrangePi Zero 2
                            │
                            └─ usbport assigns stable IP to usb0
                               Pi Zero is reachable at that address
                               Node agent runs on both, each serves its own sensors
```

The Pi Zero 2W runs its own animontics node agent. Its sensor data is accessible from the OrangePi (or any other fleet node) by connecting to the Pi Zero's USB-assigned IP.
