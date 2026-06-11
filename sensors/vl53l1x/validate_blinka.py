# SPDX-License-Identifier: MIT
"""I2C bus scan for Orange Pi Zero 2 (Blinka)."""

import board
import busio

print("Initializing I2C on SDA=PH5, SCL=PH4 ...")

with busio.I2C(board.SCL, board.SDA) as i2c:
    # Wait for bus lock
    while not i2c.try_lock():
        pass

    try:
        devices = i2c.scan()
    finally:
        i2c.unlock()

if devices:
    print(f"Found {len(devices)} device(s):")
    for addr in devices:
        print(f"  0x{addr:02X}  ({addr})")
else:
    print("No I2C devices found.")
