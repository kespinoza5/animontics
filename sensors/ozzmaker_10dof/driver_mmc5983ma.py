"""MMC5983MA 3-axis magnetometer driver.

Register-level I2C reads via smbus2. 18-bit resolution (16-bit for each axis
plus 2 extra bits shared in the XYZ2 register).

Datasheet: MEMSIC DS-MMC5983MA-02, Rev A. Address: 0x30 (fixed).
"""
from __future__ import annotations

from typing import Any

I2C_ADDR = 0x30

# Register map
_XOUT0    = 0x00   # X MSByte
_XOUT1    = 0x01   # X 2nd Byte
_YOUT0    = 0x02
_YOUT1    = 0x03
_ZOUT0    = 0x04
_ZOUT1    = 0x05
_XYZOUT2  = 0x06   # bits[7:6]=X[1:0], [5:4]=Y[1:0], [3:2]=Z[1:0]
_STATUS   = 0x08   # bit 0 = Meas_M_Done
_INT_CTRL0 = 0x09  # bit 0 = TM_M (take measurement)
_INT_CTRL2 = 0x0B  # continuous mode register
_PROD_ID   = 0x2F  # expected 0x30

# 18-bit full-scale = ±8 Gauss → 0.25 mG/LSB  (4096 LSB / mG in ±8G range)
# Zero-field output code = 2^17 = 131072 (unsigned 18-bit mid-scale)
_SCALE = 1.0 / 16384.0  # Gauss per LSB (18-bit, ±8 G full scale)
_ZERO  = 1 << 17         # 131072 — subtract to get signed value


def init(bus, addr: int = I2C_ADDR) -> None:
    """Verify product id; no persistent config needed (one-shot measurements used)."""
    prod_id = bus.read_byte_data(addr, _PROD_ID)
    if prod_id != 0x30:
        raise OSError(f"MMC5983MA PROD_ID: expected 0x30, got 0x{prod_id:02X}")


def _take_measurement(bus, addr: int) -> None:
    """Trigger a single measurement and wait for completion."""
    import time
    bus.write_byte_data(addr, _INT_CTRL0, 0x01)  # TM_M = 1
    # Measurement takes ~1.5 ms; poll status bit
    for _ in range(20):
        time.sleep(0.001)
        if bus.read_byte_data(addr, _STATUS) & 0x01:
            return
    raise TimeoutError("MMC5983MA measurement timeout")


def read(bus, addr: int = I2C_ADDR) -> dict[str, Any]:
    """Read all three axes. Returns Gauss values."""
    _take_measurement(bus, addr)
    data = bus.read_i2c_block_data(addr, _XOUT0, 7)

    xyz2 = data[6]
    x = ((data[0] << 10) | (data[1] << 2) | ((xyz2 >> 6) & 0x03)) - _ZERO
    y = ((data[2] << 10) | (data[3] << 2) | ((xyz2 >> 4) & 0x03)) - _ZERO
    z = ((data[4] << 10) | (data[5] << 2) | ((xyz2 >> 2) & 0x03)) - _ZERO

    return {
        "mag_x": round(x * _SCALE, 6),
        "mag_y": round(y * _SCALE, 6),
        "mag_z": round(z * _SCALE, 6),
    }
