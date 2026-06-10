"""LSM6DSL 6-DOF IMU (accelerometer + gyroscope) driver.

Register-level I2C reads via smbus2. All hardware-specific imports are inside
functions so this module loads cleanly on machines without smbus2.

Datasheet: ST UM2367, AN5006. Default address 0x6A (SA0=GND); 0x6B if SA0=VCC.
OzzMaker LTE-M board has SA0 pulled low → address 0x6A.
"""
from __future__ import annotations

from typing import Any

I2C_ADDR = 0x6A

# Register map
_WHO_AM_I  = 0x0F
_CTRL1_XL  = 0x10   # accel: ODR, FS
_CTRL2_G   = 0x11   # gyro: ODR, FS
_CTRL3_C   = 0x12   # SW reset, BDU
_OUT_TEMP_L = 0x20
_OUTX_L_G  = 0x22   # gyro X low (then XH, YL, YH, ZL, ZH)
_OUTX_L_XL = 0x28   # accel X low (then XH, YL, YH, ZL, ZH)

# Sensitivity constants (per datasheet Table 2 / Table 3)
# Accel FS=±2g → 0.061 mg/LSB; Gyro FS=125 dps → 4.375 mdps/LSB
_ACCEL_SENS = 0.061e-3 * 9.80665  # m/s² per LSB  (±2g range)
_GYRO_SENS  = 4.375e-3             # dps per LSB   (125 dps range)
_TEMP_SENS  = 1.0 / 256.0          # °C per LSB, offset 25°C


def init(bus, addr: int = I2C_ADDR) -> None:
    """Configure the LSM6DSL for continuous read at 104 Hz, ±2g / 125 dps."""
    who = bus.read_byte_data(addr, _WHO_AM_I)
    if who != 0x6A:
        raise OSError(f"LSM6DSL WHO_AM_I: expected 0x6A, got 0x{who:02X}")
    # SW reset; wait for it to clear
    bus.write_byte_data(addr, _CTRL3_C, 0x01)
    import time; time.sleep(0.01)
    # Accel: 104 Hz, ±2g (CTRL1_XL = 0x40)
    bus.write_byte_data(addr, _CTRL1_XL, 0x40)
    # Gyro:  104 Hz, 125 dps (CTRL2_G  = 0x42)
    bus.write_byte_data(addr, _CTRL2_G, 0x42)
    # BDU on (block data update) — CTRL3_C bit 6
    bus.write_byte_data(addr, _CTRL3_C, 0x40)


def _s16(lo: int, hi: int) -> int:
    raw = (hi << 8) | lo
    return raw - 0x10000 if raw & 0x8000 else raw


def read(bus, addr: int = I2C_ADDR) -> dict[str, Any]:
    """Read accelerometer, gyroscope, and die temperature. Returns SI units."""
    raw_g = bus.read_i2c_block_data(addr, _OUTX_L_G, 6)
    raw_a = bus.read_i2c_block_data(addr, _OUTX_L_XL, 6)
    raw_t = bus.read_i2c_block_data(addr, _OUT_TEMP_L, 2)

    gx = _s16(raw_g[0], raw_g[1]) * _GYRO_SENS
    gy = _s16(raw_g[2], raw_g[3]) * _GYRO_SENS
    gz = _s16(raw_g[4], raw_g[5]) * _GYRO_SENS

    ax = _s16(raw_a[0], raw_a[1]) * _ACCEL_SENS
    ay = _s16(raw_a[2], raw_a[3]) * _ACCEL_SENS
    az = _s16(raw_a[4], raw_a[5]) * _ACCEL_SENS

    t_raw = _s16(raw_t[0], raw_t[1])
    temp_c = round(t_raw * _TEMP_SENS + 25.0, 2)

    return {
        "accel_x": round(ax, 5),
        "accel_y": round(ay, 5),
        "accel_z": round(az, 5),
        "gyro_x": round(gx, 4),
        "gyro_y": round(gy, 4),
        "gyro_z": round(gz, 4),
        "imu_temp_c": temp_c,
    }
