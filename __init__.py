try:
    from sensors.pressure_array.sensor import PressureArray
except ImportError:
    pass  # pyserial absent on Windows dev — skip gracefully

#: A logical analog array fed by one or more MCU devices (the cranial-pressure
#: surface spans 4 MCUs). Device-fed: channels carry device+index, no connection.
METADATA = {
    "type": "pressure_array",
    "name": "Pressure sensor array (via MCU-hosted ADS1115)",
    "description": "Logical array of pressure transducers read as raw ADC over one "
                   "or more MCU serial uplinks (CircuitPython MCUs + ADS1115). May "
                   "span several devices; see config/mcus/<id>.yaml + docs/forge.md.",
    "connection": {
        "supported": [],          # device-fed array; no direct connection
        "defaults": {},
        "valid": {},
    },
    "data_keys": {
        "seq": "int   — most recent device frame sequence number",
        "raw": "dict[str,int]   — raw ADC counts keyed by pressure signal",
        "kpa": "dict[str,float] — kPa per signal when calibration.type == 'linear'",
    },
}

__all__ = ["PressureArray", "METADATA"]
