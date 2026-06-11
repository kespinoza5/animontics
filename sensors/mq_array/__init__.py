try:
    from sensors.mq_array.sensor import MqArray
except ImportError:
    pass  # pyserial not available on Windows dev machines — skip gracefully

#: Hardware constraints and defaults for the fleet tool.
#: The per-channel gas/calibration map (the `channels` list) is wiring and lives
#: in the board config, authored alongside the MCU's config/mcus/<id>.yaml.
METADATA = {
    "type": "mq_array",
    "name": "MQ gas sensor array (analog, via MCU)",
    "description": (
        "Array of MQ-series gas sensors read as raw ADC over a microcontroller "
        "serial uplink (the forge link protocol). Fed by an MCU built with "
        "tools/forge; see config/mcus/<id>.yaml."
    ),
    "connection": {
        "supported": ["uart", "usb_cdc"],
        "defaults": {
            "baud_rate": 115200,
        },
        "valid": {
            "baud_rate": [115200],
        },
    },
    "data_keys": {
        "seq":   "int   — uplink frame sequence number (0..255, wraps)",
        "raw":   "dict[str,int]   — raw ADC counts keyed by gas signal (e.g. mq135)",
        "ratio": "dict[str,float] — Rs/R0 per signal when calibration.type == 'mq' (else absent)",
    },
}

__all__ = ["MqArray", "METADATA"]
