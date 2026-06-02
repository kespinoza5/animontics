from sensors.lv_maxsonar.sensor import LVMaxSonarSensor

#: Hardware constraints and defaults for the fleet tool.
#: Connection details (actual port/baud used) live in the board's config.yaml.
METADATA = {
    "type": "lv_maxsonar",
    "name": "MaxBotix LV-MaxSonar-EZ",
    "description": "Ultrasonic distance sensor, range up to 6.45 m.",
    "connection": {
        "supported": ["uart", "usb_cdc"],
        "defaults": {
            "baud_rate": 9600,
        },
        "valid": {
            # baud_rate is fixed in hardware
            "baud_rate": [9600],
        },
    },
    "data_keys": {
        "distance_mm": "int  — measured distance in millimetres",
        "strength":    "None — not provided by this sensor",
        "temp_c":      "None — not provided by this sensor",
    },
}

__all__ = ["LVMaxSonarSensor", "METADATA"]
