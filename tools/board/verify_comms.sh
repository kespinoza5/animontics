#!/usr/bin/env bash
# verify_comms.sh — Verify hardware communication interfaces on this board.
#
# Scans I2C buses, lists UART devices, and enumerates USB serial devices.
# Run this after initial board setup to confirm sensors are wired correctly.
#
# Usage:
#   ./tools/board/verify_comms.sh
#
# Requirements: i2c-tools (sudo apt install i2c-tools)

set -euo pipefail

echo "========================================"
echo "  Animontics — Hardware Comms Verify"
echo "========================================"
echo ""

# ── I2C ──────────────────────────────────────────────────────────────────────

echo "── I2C Buses ────────────────────────────"
I2C_BUSES=$(ls /dev/i2c-* 2>/dev/null || true)
if [[ -z "$I2C_BUSES" ]]; then
    echo "  No I2C buses found."
    echo "  Run: tools/board/setup_i2c.sh"
else
    for bus_path in $I2C_BUSES; do
        bus_num="${bus_path##*-}"
        echo ""
        echo "  /dev/i2c-$bus_num:"
        if command -v i2cdetect &>/dev/null; then
            i2cdetect -y -r "$bus_num" 2>/dev/null | sed 's/^/    /'
        else
            echo "    i2cdetect not found — run: sudo apt install i2c-tools"
        fi
    done
fi

echo ""

# ── UART ─────────────────────────────────────────────────────────────────────

echo "── UART / Serial Devices ────────────────"
UART_DEVS=$(ls /dev/ttyAMA* /dev/ttyS* /dev/ttyO* 2>/dev/null | grep -v "ttyS[2-9][0-9]" || true)
if [[ -z "$UART_DEVS" ]]; then
    echo "  No hardware UART devices found."
else
    for dev in $UART_DEVS; do
        if [[ -e "$dev" ]]; then
            echo "  $dev"
        fi
    done
fi

echo ""

# ── USB CDC / Serial ─────────────────────────────────────────────────────────

echo "── USB CDC / Serial (ttyACM*, ttyUSB*) ──"
USB_DEVS=$(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || true)
if [[ -z "$USB_DEVS" ]]; then
    echo "  No USB serial devices found."
else
    for dev in $USB_DEVS; do
        # Try to get USB device info
        base="${dev##*/}"
        vid_pid=$(cat /sys/class/tty/"$base"/device/idVendor 2>/dev/null && \
                  echo ":" && \
                  cat /sys/class/tty/"$base"/device/idProduct 2>/dev/null || echo "")
        product=$(cat /sys/class/tty/"$base"/device/product 2>/dev/null || echo "")
        echo "  $dev  ${vid_pid:+(${vid_pid})}  ${product}"
    done
fi

echo ""

# ── USB Devices Summary ───────────────────────────────────────────────────────

echo "── All USB Devices ──────────────────────"
if command -v lsusb &>/dev/null; then
    lsusb | sed 's/^/  /'
else
    echo "  lsusb not found — run: sudo apt install usbutils"
fi

echo ""
echo "========================================"
echo "  Done."
echo "========================================"
