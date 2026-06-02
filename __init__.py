try:
    from sensors.mlx90640.sensor import MLX90640Sensor
except ImportError:
    pass  # smbus2 / Blinka not available on dev machines — skip gracefully

#: Hardware constraints and defaults for the fleet tool.
#: Connection details (actual bus/address used) live in the board's config.yaml.
METADATA = {
    "type": "mlx90640",
    "name": "Melexis MLX90640 32×24 Thermal Array",
    "description": "Far-infrared thermal camera, 32×24 pixels, −40 to +300 °C.",
    "connection": {
        "supported": ["i2c"],
        "defaults": {
            "bus":     3,
            "address": 0x33,
        },
        "valid": {
            "address": [0x33],  # fixed in silicon
        },
        "notes": "Requires I2C Fast Mode (400 kHz) or Fast Mode+ (1 MHz).",
    },
    "data_keys": {
        "pixels":   "list[float] — 768 temperature values (32×24, row-major) in °C",
        "min_temp": "float       — minimum pixel temperature in °C",
        "max_temp": "float       — maximum pixel temperature in °C",
        "width":    "int         — always 32",
        "height":   "int         — always 24",
    },
}

__all__ = ["MLX90640Sensor", "METADATA"]
