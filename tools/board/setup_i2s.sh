#!/usr/bin/env bash
# setup_i2s.sh — Enable the I2S audio bus on a Raspberry Pi.
#
# Run on the board as root. Enables the I2S interface for digital audio
# peripherals (MEMS mics, DACs). Edits the firmware config.txt idempotently.
# A reboot is required.
#
# Usage:
#   sudo ./tools/board/setup_i2s.sh                      # enable the I2S interface
#   sudo ./tools/board/setup_i2s.sh --overlay googlevoicehat-soundcard
#                                                        # also load a device overlay
#
# Many I2S peripherals need a matching dtoverlay in addition to dtparam=i2s=on.
# Pass it with --overlay; look up the correct name in
# /boot/firmware/overlays/README on the board.
#
# Note: Raspberry Pi only. Orange Pi / Armbian use `armbian-config`.

set -euo pipefail
source "$(dirname "$0")/lib_config.sh"

OVERLAY=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --overlay) OVERLAY="${2:-}"; shift 2 ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)         die "unknown argument: $1" ;;
    esac
done

require_root "$@"

echo "========================================"
echo "  Animontics — Enable I2S Audio"
echo "========================================"
echo ""

CONFIG=$(find_config_txt)
info "using $CONFIG"

ensure_line "$CONFIG" "dtparam=i2s=on" "^[[:space:]]*#?[[:space:]]*dtparam=i2s=.*"

if [[ -n "$OVERLAY" ]]; then
    ensure_line "$CONFIG" "dtoverlay=${OVERLAY}"
fi

reboot_notice
