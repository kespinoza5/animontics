#!/usr/bin/env bash
# setup_i2c.sh — Enable the I2C bus on a Raspberry Pi and set its speed.
#
# Run on the board as root. Edits the firmware config.txt idempotently and
# loads the i2c-dev module so /dev/i2c-* appears. A reboot is required.
#
# Usage:
#   sudo ./tools/board/setup_i2c.sh                 # enable at default 100 kHz
#   sudo ./tools/board/setup_i2c.sh --baudrate 400000   # fast-mode I2C
#
# After reboot, confirm with: tools/board/verify_comms.sh
#
# Note: Raspberry Pi only. Orange Pi / Armbian use `armbian-config`.

set -euo pipefail
source "$(dirname "$0")/lib_config.sh"

BAUDRATE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --baudrate) BAUDRATE="${2:-}"; shift 2 ;;
        -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)          die "unknown argument: $1" ;;
    esac
done

require_root "$@"

echo "========================================"
echo "  Animontics — Enable I2C"
echo "========================================"
echo ""

CONFIG=$(find_config_txt)
info "using $CONFIG"

# Enable the ARM I2C controller.
ensure_line "$CONFIG" "dtparam=i2c_arm=on" "^[[:space:]]*#?[[:space:]]*dtparam=i2c_arm=.*"

# Optional bus speed.
if [[ -n "$BAUDRATE" ]]; then
    [[ "$BAUDRATE" =~ ^[0-9]+$ ]] || die "baudrate must be an integer, got: $BAUDRATE"
    ensure_line "$CONFIG" "dtparam=i2c_arm_baudrate=${BAUDRATE}" \
                "^[[:space:]]*#?[[:space:]]*dtparam=i2c_arm_baudrate=.*"
fi

# Ensure the userspace device node is created on boot.
ensure_line /etc/modules "i2c-dev"

# Try to load it now so a reboot isn't strictly needed to test wiring.
if modprobe i2c-dev 2>/dev/null; then
    ok "i2c-dev module loaded"
fi

if ! command -v i2cdetect &>/dev/null; then
    warn "i2c-tools not installed — run: sudo apt install i2c-tools"
fi

reboot_notice
