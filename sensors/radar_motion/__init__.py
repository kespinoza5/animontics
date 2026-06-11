try:
    from sensors.radar_motion.sensor import RadarMotion
except ImportError:
    pass  # hardware deps not available on this platform

#: Microwave Doppler motion (analog-hacked RCWL-0516). Device-fed array:
#: channels carry device+index (ADS1115 or MCU uplink), no connection.
METADATA = {
    "type": "radar_motion",
    "name": "Microwave radar motion (RCWL-0516, analog-hacked)",
    "description": "Doppler motion level from RCWL-0516 modules hacked to expose "
                   "their analog stage, read via an ADS1115 device or MCU uplink. "
                   "Per-channel EMA baseline + deviation threshold in Python.",
    "connection": {
        "supported": [],          # device-fed array; no direct connection
        "defaults": {},
        "valid": {},
    },
    "data_keys": {
        "seq": "int — most recent device frame sequence number",
        "raw": "dict[str,int] — raw ADC counts keyed by radar signal",
        "level": "dict[str,float] — |deviation| from the adaptive resting baseline",
        "motion": "dict[str,bool] — level > params.threshold per channel",
    },
}

__all__ = ["RadarMotion", "METADATA"]
