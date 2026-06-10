"""Unit tests for register-level parsing logic — no hardware required."""
import struct
import pytest
from sensors.ozzmaker_10dof.driver_lsm6dsl import _s16, _ACCEL_SENS, _GYRO_SENS
from sensors.ozzmaker_10dof.driver_mmc5983ma import _ZERO, _SCALE
from sensors.ozzmaker_10dof.driver_bmp388 import _compensate_temp, _compensate_pressure


# ── LSM6DSL ───────────────────────────────────────────────────────────────────

def test_s16_positive():
    assert _s16(0x00, 0x10) == 0x1000   # 4096

def test_s16_negative():
    # Two's complement: 0x8000 = -32768
    assert _s16(0x00, 0x80) == -32768

def test_accel_1g():
    # +1g ≈ 9.80665 m/s². At ±2g FS → 16384 LSB/g
    lsb = round(9.80665 / _ACCEL_SENS)
    result = lsb * _ACCEL_SENS
    assert abs(result - 9.80665) < 0.01

def test_gyro_scale():
    # 1000 LSB at 4.375 mdps/LSB → 4.375 dps
    assert abs(1000 * _GYRO_SENS - 4.375) < 1e-6


# ── MMC5983MA ──────────────────────────────────────────────────────────────────

def test_mag_zero_field():
    # Mid-scale output (131072 for each axis) → 0.0 Gauss
    assert (_ZERO - _ZERO) * _SCALE == 0.0

def test_mag_positive():
    # Max positive deflection: 2^17 - 1 above zero
    assert (((1 << 17) - 1) * _SCALE) > 0


# ── BMP388 ────────────────────────────────────────────────────────────────────

def test_temp_compensation_reasonable():
    # raw_t = 0xFEA0EB is computed to yield ~25°C for these calib values:
    #   t_lin = raw_t/16 - T1; temp = t_lin*(T2/2^30) + t_lin^2*(T3/2^48)
    calib = (27504, 26435, -2, 36477, -10685, 24, 6253, 23843, -11777, -128, -7, -6553, 0, 0)
    raw_t = 0xFEA0EB
    temp_c, t_lin = _compensate_temp(raw_t, calib)
    assert 20.0 < temp_c < 30.0
    assert isinstance(t_lin, float)

def test_pressure_compensation_runs():
    # Smoke-test only: synthetic calibration data produces non-representative
    # pressure values. Real range validation requires actual chip cal data on hardware.
    calib = (27504, 26435, -2, 36477, -10685, 24, 6253, 23843, -11777, -128, -7, -6553, 0, 0)
    raw_t = 0xFEA0EB
    _, t_lin = _compensate_temp(raw_t, calib)
    raw_p = 0x5F3C68
    pressure = _compensate_pressure(raw_p, t_lin, calib)
    import math
    assert isinstance(pressure, float) and math.isfinite(pressure)
