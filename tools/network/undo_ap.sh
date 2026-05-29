#!/usr/bin/env bash
# undo-ap.sh — run on the Pi as root (sudo bash undo-ap.sh)
# Tears down the animontics AP and restores wlan0 to its previous state.
set -euo pipefail

AP_CON="animontics-ap"
SERVICE="animontics-dashboard"

echo "=== [1/4] Stopping dashboard service ==="
systemctl stop "$SERVICE" 2>/dev/null && echo "    Stopped" || echo "    (not running)"
systemctl disable "$SERVICE" 2>/dev/null && echo "    Disabled" || true
rm -f "/etc/systemd/system/${SERVICE}.service"
systemctl daemon-reload
echo "    Service removed"

echo ""
echo "=== [2/4] Taking down AP connection ==="
nmcli connection down "$AP_CON" 2>/dev/null && echo "    Brought down $AP_CON" || echo "    (not active)"
nmcli connection delete "$AP_CON" 2>/dev/null && echo "    Deleted $AP_CON" || echo "    (not found)"

echo ""
echo "=== [3/4] Restoring previous wlan0 connection ==="
# Find any non-AP wifi connection that isn't the AP we just removed
PREV=$(nmcli -t -f NAME,TYPE connection show | grep ":wifi$" | cut -d: -f1 | head -1 || true)
if [ -n "$PREV" ]; then
    echo "    Bringing up: $PREV"
    nmcli connection up "$PREV" && echo "    wlan0 restored to: $PREV" || \
        echo "    Could not auto-connect. Run: nmcli device wifi connect <SSID> password <PASS>"
else
    echo "    No saved wifi profile found."
    echo "    Reconnect manually: nmcli device wifi connect <SSID> password <PASS>"
fi

echo ""
echo "=== [4/4] Optional: remove installed files ==="
echo "    Dashboard files left in /opt/animontics — remove manually if desired:"
echo "      sudo rm -rf /opt/animontics"

echo ""
echo "========================================"
echo "Undo complete."
echo "========================================"
