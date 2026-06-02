from sensors.tf_mini.sensor import TFminiSensor

#: Hardware constraints and defaults for the fleet tool.
#: Connection details (actual port/baud used) live in the board's config.yaml.
METADATA = {
    "type": "tf_mini",
    "name": "Benewake TF Mini Plus LiDAR",
    "description": "Single-point LiDAR distance sensor, range up to 12 m.",
    "connection": {
        "supported": ["uart", "usb_cdc"],
        "defaults": {
            "baud_rate": 115200,
        },
        "valid": {
            # baud_rate is fixed in hardware; other values will not work
            "baud_rate": [115200],
        },
    },
    "data_keys": {
        "distance_mm": "int   — measured distance in millimetres",
        "strength":    "int   — signal quality / return strength",
        "temp_c":      "float — sensor internal temperature in °C",
    },
}

__all__ = ["TFminiSensor", "METADATA"]
