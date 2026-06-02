try:
    from sensors.vl53l1x.sensor import VL53L1XSensor
except ImportError:
    pass  # smbus2 / Blinka not available on dev machines — skip gracefully

#: Hardware constraints and defaults for the fleet tool.
#: Connection details (actual bus/address used) live in the board's config.yaml.
METADATA = {
    "type": "vl53l1x",
    "name": "ST VL53L1X Time-of-Flight",
    "description": "Time-of-flight distance sensor, range up to 4 m (long mode).",
    "connection": {
        "supported": ["i2c"],
        "defaults": {
            "bus":     3,
            "address": 0x29,
        },
        "valid": {
            # Address is fixed in silicon; changing it requires toggling XSHUT
            # and issuing an I2C address-change command before the next sensor boots.
            "address": [0x29],
        },
        "notes": "Multiple sensors on one bus require per-sensor XSHUT address assignment.",
    },
    "data_keys": {
        "distance_mm": "int | None — distance in mm; None on ranging error or out-of-range",
        "strength":    "None — not provided by this sensor",
        "temp_c":      "None — not provided by this sensor",
    },
}

__all__ = ["VL53L1XSensor", "METADATA"]
