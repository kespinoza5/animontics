#!/usr/bin/env bash
# setup_spi.sh — Enable the SPI bus on a Raspberry Pi.
#
# Run on the board as root. Edits the firmware config.txt idempotently so the
# /dev/spidev* device nodes appear. A reboot is required.
#
# Usage:
#   sudo ./tools/board/setup_spi.sh
#
# After reboot, confirm the device nodes exist:
#   ls /dev/spidev*
#
# Note: Raspberry Pi only. Orange Pi / Armbian use `armbian-config`.

set -euo pipefail
source "$(dirname "$0")/lib_config.sh"

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

require_root "$@"

echo "========================================"
echo "  Animontics — Enable SPI"
echo "========================================"
echo ""

CONFIG=$(find_config_txt)
info "using $CONFIG"

ensure_line "$CONFIG" "dtparam=spi=on" "^[[:space:]]*#?[[:space:]]*dtparam=spi=.*"

reboot_notice
echo "  After reboot, check: ls /dev/spidev*"
