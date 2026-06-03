# tools/network

Scripts for configuring WiFi on boards that act as access points.

## Tools

### `setup_ap.sh`

Configures the board as a WiFi access point using `hostapd` and `dnsmasq`. Used for boards that need to create their own network segment (e.g. an OrangePi acting as a local hub for nearby devices).

The AP passphrase is **not** stored in the script. Provide it via a gitignored
secrets file or the environment (see [AP credentials](#ap-credentials) below).

```bash
# Copy the script and your secrets file to the board, then run
scp tools/network/setup_ap.sh ap.secrets pi@<board-ip>:/tmp/
ssh pi@<board-ip> 'cd /tmp && chmod +x setup_ap.sh && sudo bash setup_ap.sh'
```

### `undo_ap.sh`

Reverts the AP configuration applied by `setup_ap.sh`, restoring the board to normal WiFi client mode.

```bash
scp tools/network/undo_ap.sh pi@<board-ip>:/tmp/
ssh pi@<board-ip> 'chmod +x /tmp/undo_ap.sh && sudo /tmp/undo_ap.sh'
```

## AP credentials

`setup_ap.sh` never hardcodes the AP passphrase. It resolves credentials in this
order:

1. A gitignored secrets file. By default `tools/network/ap.secrets` (next to the
   script), or wherever `ANIMONTICS_AP_SECRETS` points. It is shell-sourced, so
   it must use shell syntax:

   ```bash
   AP_SSID="animontics"          # optional, defaults to "animontics"
   AP_PASS="your-wpa2-passphrase"  # required, 8-63 chars
   ```

   Copy [`ap.secrets.example`](ap.secrets.example) to `ap.secrets` and fill it in.

2. The environment, when no file is present:

   ```bash
   AP_PASS='your-wpa2-passphrase' sudo -E bash setup_ap.sh
   ```

`*.secrets` and `tools/network/ap.secrets` are gitignored. The script exits with
a clear error if `AP_PASS` is unset or not a valid 8-63 character WPA2 passphrase.

## Which Boards Need This

See the [tools/README.md](../README.md) deployment guide.
