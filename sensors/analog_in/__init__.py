try:
    from sensors.analog_in.sensor import AnalogIn
except ImportError:
    pass

#: Heterogeneous scalar analog inputs via a pull device (ADS1115). In-tree: generic
#: SBC-side utility. Channels are device-fed (no connection); each is its own signal.
METADATA = {
    "type": "analog_in",
    "name": "Analog input(s) via ADS1115 (per-channel signals)",
    "description": "Reads individual ADS1115 channels through a shared device; "
                   "each channel is a distinct signal with its own calibration.",
    "connection": {
        "supported": [],          # device-fed, no direct connection
        "defaults": {},
        "valid": {},
    },
    "data_keys": {
        "raw":        "dict[str,int]   — raw ADC counts keyed by signal",
        "<signal>":   "float — calibrated value when that channel's calibration is 'linear'",
    },
}

__all__ = ["AnalogIn", "METADATA"]
