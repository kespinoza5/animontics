#!/usr/bin/env bash
# install.sh — run on the Pi as root (sudo bash install.sh)
# Sets up the animontics Wi-Fi AP and the sensor dashboard service.
set -euo pipefail

AP_CON="animontics-ap"
PI_IP="192.168.50.1/24"
INSTALL_DIR="/opt/animontics"
SERVICE="animontics-dashboard"

# AP credentials are NOT hardcoded. Source them from a gitignored secrets file
# (shell-sourceable, e.g. tools/network/ap.secrets) or from the environment.
# The file/env must define AP_PASS; AP_SSID is optional (defaults to "animontics").
#   AP_SSID="animontics"
#   AP_PASS="<your-wpa2-passphrase>"
AP_SECRETS_FILE="${ANIMONTICS_AP_SECRETS:-$(dirname "$0")/ap.secrets}"
if [ -f "$AP_SECRETS_FILE" ]; then
    # shellcheck disable=SC1090
    . "$AP_SECRETS_FILE"
fi
AP_SSID="${AP_SSID:-animontics}"
if [ -z "${AP_PASS:-}" ]; then
    echo "ERROR: AP_PASS is not set." >&2
    echo "  Provide it via the environment (AP_PASS=... sudo -E bash setup_ap.sh)" >&2
    echo "  or in a gitignored secrets file: $AP_SECRETS_FILE" >&2
    echo "  (set ANIMONTICS_AP_SECRETS to point elsewhere)." >&2
    exit 1
fi
if [ "${#AP_PASS}" -lt 8 ] || [ "${#AP_PASS}" -gt 63 ]; then
    echo "ERROR: AP_PASS must be 8-63 characters (WPA2 passphrase requirement)." >&2
    exit 1
fi

echo "=== [1/5] Installing dashboard files ==="
mkdir -p "$INSTALL_DIR/static"
cp dashboard.py camera.py sensors.py i2c.py "$INSTALL_DIR/"
cp static/index.html "$INSTALL_DIR/static/"
echo "    Copied modules and static/ -> $INSTALL_DIR/"

echo ""
echo "=== [2/5] Installing systemd service ==="
cp animontics-dashboard.service "/etc/systemd/system/${SERVICE}.service"
systemctl daemon-reload
systemctl enable "$SERVICE"
echo "    Service enabled (will start after AP is up)"

echo ""
echo "=== [3/5] Configuring Wi-Fi AP on wlan0 ==="
# System dnsmasq conflicts with NM's built-in DHCP server on the AP interface
if systemctl is-active --quiet dnsmasq; then
    echo "    Stopping system dnsmasq (conflicts with NM's DHCP)"
    systemctl stop dnsmasq
fi
systemctl disable dnsmasq 2>/dev/null || true
# Deactivate existing wlan0 connection without deleting it (keeps undo clean)
EXISTING=$(nmcli -t -f NAME,DEVICE connection show --active | grep ":wlan0" | cut -d: -f1 || true)
if [ -n "$EXISTING" ]; then
    echo "    Deactivating existing connection: $EXISTING"
    nmcli connection down "$EXISTING" || true
fi

# Remove stale AP connection if a previous install left one
nmcli connection delete "$AP_CON" 2>/dev/null && echo "    Removed stale $AP_CON" || true

nmcli connection add \
    type wifi \
    ifname wlan0 \
    con-name "$AP_CON" \
    autoconnect yes \
    ssid "$AP_SSID" \
    mode ap \
    wifi.band bg \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$AP_PASS" \
    ipv4.method shared \
    ipv4.addresses "$PI_IP"
echo "    Created connection: $AP_CON (SSID=$AP_SSID)"

echo ""
echo "=== [4/5] Bringing up AP ==="
nmcli connection up "$AP_CON"
echo "    AP is live. Pi IP on AP network: ${PI_IP%/*}"

echo ""
echo "=== [5/5] Starting dashboard service ==="
systemctl start "$SERVICE"
sleep 2
systemctl status "$SERVICE" --no-pager

echo ""
echo "========================================"
echo "Done!"
echo "  AP SSID : $AP_SSID"
echo "  Password : (from $AP_SECRETS_FILE / environment — not printed)"
echo "  Dashboard: http://${PI_IP%/*}:8080"
echo ""
echo "To undo everything: sudo bash undo-ap.sh"
echo "========================================"
