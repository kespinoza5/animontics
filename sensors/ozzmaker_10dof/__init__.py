try:
    from sensors.ozzmaker_10dof.sensor import OzzMaker10DofSensor
except ImportError:
    pass  # smbus2 not available on Windows dev machines

#: Hardware constraints and defaults for the fleet tool.
METADATA = {
    "type": "ozzmaker_10dof",
    "name": "OzzMaker LTE-M GPS + 10DOF (IMU + Mag + Baro)",
    "description": (
        "LSM6DSL 6-DOF IMU (accel + gyro), MMC5983MA 3-axis magnetometer, and "
        "BMP388 barometric pressure sensor on the OzzMaker LTE-M GPS + 10DOF board."
    ),
    "connection": {
        "supported": ["i2c"],
        "defaults": {
            "bus": 3,
        },
        "notes": (
            "All three chips share one I2C bus. Addresses are fixed silicon: "
            "LSM6DSL=0x6A, MMC5983MA=0x30, BMP388=0x77."
        ),
    },
    "data_keys": {
        "accel_x":    "float — X-axis acceleration (m/s²)",
        "accel_y":    "float — Y-axis acceleration (m/s²)",
        "accel_z":    "float — Z-axis acceleration (m/s²)",
        "gyro_x":     "float — X-axis angular velocity (dps)",
        "gyro_y":     "float — Y-axis angular velocity (dps)",
        "gyro_z":     "float — Z-axis angular velocity (dps)",
        "imu_temp_c": "float — LSM6DSL die temperature (°C)",
        "mag_x":      "float — X-axis magnetic field (Gauss)",
        "mag_y":      "float — Y-axis magnetic field (Gauss)",
        "mag_z":      "float — Z-axis magnetic field (Gauss)",
        "pressure_pa": "float — atmospheric pressure (Pa)",
        "temp_c":      "float — BMP388 temperature (°C)",
        "altitude_m":  "float — ISA altitude estimate (m)",
    },
}

__all__ = ["OzzMaker10DofSensor", "METADATA"]
