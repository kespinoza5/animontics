try:
    from sensors.fan_tach.sensor import FanTach
except ImportError:
    pass

#: Fan RPM from an MCU's tach (FG) counters. Device-fed (channels carry
#: device+index); the firmware `tach` module already converts edges → RPM.
METADATA = {
    "type": "fan_tach",
    "name": "Fan tach (RPM) via MCU FG counters",
    "description": "Reads fan FG pulses on a CircuitPython MCU (countio) and "
                   "streams RPM; consumed as a device-fed array sensor.",
    "connection": {
        "supported": [],
        "defaults": {},
        "valid": {},
    },
    "data_keys": {
        "seq": "int   — uplink frame sequence number",
        "raw": "dict[str,int] — RPM per fan signal (raw frame value is already RPM)",
        "rpm": "dict[str,int] — alias of raw, the per-fan RPM",
    },
}

__all__ = ["FanTach", "METADATA"]
