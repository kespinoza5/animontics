"""BMP388 barometric pressure and temperature sensor driver.

Register-level I2C reads via smbus2, with factory calibration compensation
per the BMP388 datasheet (BST-BMP388-DS001-07, Section 8.5).

Default I2C address 0x77 (SDO=VCC); 0x76 if SDO=GND.
"""
from __future__ import annotations

import struct
from typing import Any

I2C_ADDR = 0x77

# Register map
_CHIP_ID    = 0x00   # expected 0x50
_ERR_REG    = 0x02
_STATUS     = 0x03   # cmd_rdy, drdy_press, drdy_temp
_DATA_0     = 0x04   # pressure XLSB, LSB, MSB; temp XLSB, LSB, MSB (6 bytes)
_PWR_CTRL   = 0x1B   # [1:0] press_en, temp_en; [5:4] mode
_OSR        = 0x1C   # oversampling: [2:0]=press, [5:3]=temp
_CALIB_DATA = 0x31   # 21 bytes NVM calibration

# Power mode — 0b11 = normal, 0b10 = forced (one-shot)
_MODE_FORCED = 0x13  # press_en | temp_en | forced mode


def _read_calib(bus, addr: int):
    """Read and unpack the 21-byte NVM calibration block."""
    raw = bytes(bus.read_i2c_block_data(addr, _CALIB_DATA, 21))
    # Unpack in order per datasheet Table 19
    T1, T2 = struct.unpack_from("<HH", raw, 0)
    T3,     = struct.unpack_from("<b", raw, 4)
    P1, P2  = struct.unpack_from("<hh", raw, 5)
    P3, P4  = struct.unpack_from("<bb", raw, 9)
    P5, P6  = struct.unpack_from("<HH", raw, 11)
    P7, P8  = struct.unpack_from("<bb", raw, 15)
    P9,     = struct.unpack_from("<h", raw, 17)
    P10,    = struct.unpack_from("<b", raw, 19)
    P11,    = struct.unpack_from("<b", raw, 20)
    return (T1, T2, T3, P1, P2, P3, P4, P5, P6, P7, P8, P9, P10, P11)


def _compensate_temp(raw_t: int, calib) -> tuple[float, float]:
    """Return (temp_c, t_lin) — t_lin is the intermediate value for pressure compensation.

    Formula per BMP388 datasheet Table 21 (double precision floating point):
      var1     = adc_T / 16 - par_T1
      comp_temp = var1 * (par_T2 / 2^30) + var1^2 * (par_T3 / 2^48)
    t_lin (= var1) is passed to _compensate_pressure unchanged.
    """
    T1, T2, T3 = calib[0], calib[1], calib[2]
    t_lin = raw_t / 16.0 - T1
    temp_c = t_lin * (T2 / 1073741824.0) + t_lin * t_lin * (T3 / 281474976710656.0)
    return round(temp_c, 4), t_lin


def _compensate_pressure(raw_p: int, t_lin: float, calib) -> float:
    """Return pressure in Pa."""
    P1, P2, P3, P4, P5, P6, P7, P8, P9, P10, P11 = calib[3:14]
    partial1 = P6 / 64.0 * t_lin
    partial2 = P5 * 131072.0 + partial1
    partial3 = P4 / 32768.0 * t_lin * t_lin
    partial4 = P3 / 256.0 * t_lin * t_lin * t_lin
    out = partial2 + partial3 + partial4
    partial1 = P2 / 536870912.0 * raw_p
    partial2 = P1 / 1048576.0 * raw_p + out
    partial3 = raw_p * raw_p
    partial4 = P9 * partial3 / 281474976710656.0
    partial5 = P10 * raw_p * t_lin / 281474976710656.0
    partial6 = partial3 * raw_p * P11 / 36893488147419103232.0
    out = partial1 + partial2 + partial4 + partial5 + partial6 - P5 * 131072.0
    return round(out, 2)


class BMP388:
    """Stateful driver — holds calibration so we don't re-read it on every sample."""

    def __init__(self, bus, addr: int = I2C_ADDR):
        self._bus = bus
        self._addr = addr
        chip = bus.read_byte_data(addr, _CHIP_ID)
        if chip != 0x50:
            raise OSError(f"BMP388 CHIP_ID: expected 0x50, got 0x{chip:02X}")
        self._calib = _read_calib(bus, addr)
        # OSR: x1 for temp, x4 for pressure (good default balance)
        bus.write_byte_data(addr, _OSR, 0x01)

    def read(self) -> dict[str, Any]:
        """Trigger a forced measurement and return pressure (Pa), temp (°C), alt (m)."""
        import time
        self._bus.write_byte_data(self._addr, _PWR_CTRL, _MODE_FORCED)
        # 2 ms minimum for x1 oversampling; poll drdy bits
        for _ in range(50):
            time.sleep(0.001)
            status = self._bus.read_byte_data(self._addr, _STATUS)
            if (status & 0b00110000) == 0b00110000:  # drdy_press | drdy_temp
                break

        raw = self._bus.read_i2c_block_data(self._addr, _DATA_0, 6)
        raw_p = (raw[2] << 16) | (raw[1] << 8) | raw[0]
        raw_t = (raw[5] << 16) | (raw[4] << 8) | raw[3]

        temp_c, t_lin = _compensate_temp(raw_t, self._calib)
        pressure_pa   = _compensate_pressure(raw_p, t_lin, self._calib)
        # International standard atmosphere altitude approximation
        alt_m = round(44330.0 * (1.0 - (pressure_pa / 101325.0) ** (1.0 / 5.255)), 2)

        return {
            "pressure_pa": pressure_pa,
            "temp_c": temp_c,
            "altitude_m": alt_m,
        }
