# tools/network

Scripts for configuring WiFi on boards that act as access points.

## Tools

### `setup_ap.sh`

Configures the board as a WiFi access point using `hostapd` and `dnsmasq`. Used for boards that need to create their own network segment (e.g. an OrangePi acting as a local hub for nearby devices).

```bash
# Copy to the board and run
scp tools/network/setup_ap.sh pi@192.168.1.x:/tmp/
ssh pi@192.168.1.x 'chmod +x /tmp/setup_ap.sh && sudo /tmp/setup_ap.sh'
```

### `undo_ap.sh`

Reverts the AP configuration applied by `setup_ap.sh`, restoring the board to normal WiFi client mode.

```bash
scp tools/network/undo_ap.sh pi@192.168.1.x:/tmp/
ssh pi@192.168.1.x 'chmod +x /tmp/undo_ap.sh && sudo /tmp/undo_ap.sh'
```

## Which Boards Need This

See the [tools/README.md](../README.md) deployment guide.
