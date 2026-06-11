try:
    from sensors.current.sensor import CurrentSensor
except ImportError:
    pass  # hardware deps not available on this platform

#: Interoception — rail current via hall-effect sensors (ACS712). Device-fed
#: array: channels carry device+index (ADS1115 or MCU uplink), no connection.
METADATA = {
    "type": "current",
    "name": "Current sensor (ACS712 / hall-effect)",
    "description": "Rail current from analog hall-effect sensors read via an "
                   "ADS1115 device or MCU uplink. counts→amps calibration per "
                   "channel; pairs with the power_rail effector for the "
                   "overcurrent guard reflex.",
    "connection": {
        "supported": [],          # device-fed array; no direct connection
        "defaults": {},
        "valid": {},
    },
    "data_keys": {
        "seq": "int — most recent device frame sequence number",
        "raw": "dict[str,int] — raw ADC counts keyed by rail signal",
        "amps": "dict[str,float] — signed amps per acs712-calibrated channel",
    },
}

__all__ = ["CurrentSensor", "METADATA"]
