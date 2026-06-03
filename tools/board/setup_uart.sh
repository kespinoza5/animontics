#!/usr/bin/env bash
# setup_uart.sh — Enable the hardware UART and free it from the serial console.
#
# Run on the board as root. Many UART sensors (TF Mini, LV-MaxSonar) need the
# PL011 UART, which Raspberry Pi OS hands to a login console by default. This
# script enables the UART and removes the console so sensor traffic is clean.
# A reboot is required.
#
# Usage:
#   sudo ./tools/board/setup_uart.sh
#
# What it does:
#   - config.txt:  enable_uart=1
#   - cmdline.txt: strips `console=serial0,115200` (and ttyAMA0 variants)
#   - disables the serial-getty login service on ttyAMA0 / serial0
#
# After reboot, confirm with: tools/board/verify_comms.sh
#
# Note: Raspberry Pi only. Orange Pi / Armbian use `armbian-config`.

set -euo pipefail
source "$(dirname "$0")/lib_config.sh"

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

require_root "$@"

echo "========================================"
echo "  Animontics — Enable UART"
echo "========================================"
echo ""

CONFIG=$(find_config_txt)
CMDLINE=$(find_cmdline_txt)
info "using $CONFIG"
info "using $CMDLINE"

# 1. Enable the UART peripheral.
ensure_line "$CONFIG" "enable_uart=1" "^[[:space:]]*#?[[:space:]]*enable_uart=.*"

# 2. Remove the serial console from the kernel cmdline (single-line file).
backup_once "$CMDLINE"
if grep -Eq 'console=(serial0|ttyAMA0|ttyS0)[^ ]*' "$CMDLINE"; then
    sed -i -E 's/console=(serial0|ttyAMA0|ttyS0)[^ ]* ?//g' "$CMDLINE"
    # Collapse any double spaces / trailing space left behind.
    sed -i -E 's/  +/ /g; s/ +$//' "$CMDLINE"
    ok "removed serial console from $CMDLINE"
else
    info "no serial console entry in $CMDLINE"
fi

# 3. Disable the login getty that would otherwise hold the port open.
for unit in serial-getty@ttyAMA0.service serial-getty@serial0.service serial-getty@ttyS0.service; do
    if systemctl list-unit-files "$unit" &>/dev/null && \
       systemctl is-enabled "$unit" &>/dev/null; then
        systemctl disable "$unit" 2>/dev/null || true
        systemctl stop "$unit" 2>/dev/null || true
        ok "disabled $unit"
    fi
done

reboot_notice
