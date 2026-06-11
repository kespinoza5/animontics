try:
    from sensors.pressure_array.sensor import PressureArray
except ImportError:
    pass  # pyserial absent on Windows dev — skip gracefully

#: A logical analog array fed by one or more MCU devices — flat (static taps,
#: e.g. the cranial surface across 4 MCUs) or a scanned lattice (params.rows +
#: per-device row_tag channels; the velostat lattice scanned by matrix_scan /
#: scan_follower firmware). Device-fed: channels carry device+index, no connection.
METADATA = {
    "type": "pressure_array",
    "name": "Pressure sensor array (via MCU-hosted ADS1115)",
    "description": "Logical array of pressure transducers read as raw ADC over one "
                   "or more MCU serial uplinks (CircuitPython MCUs + ADS1115). May "
                   "span several devices, optionally as a row-scanned lattice; see "
                   "config/mcus/<id>.yaml + docs/forge.md.",
    "connection": {
        "supported": [],          # device-fed array; no direct connection
        "defaults": {},
        "valid": {},
    },
    "data_keys": {
        "seq": "int   — most recent device frame sequence number",
        "raw": "dict[str,int]   — raw ADC counts keyed by pressure signal",
        "kpa": "dict[str,float] — kPa per signal when calibration.type == 'linear'",
        "row": "dict[str,int]   — scanned lattice: current scan row per device",
        "sweep": "dict — scanned lattice: last sweep summary {n, rows, cols, "
                 "complete, missing_cells, timeouts, devices}; the full float32 "
                 "grid rides the binary frame lane (/sensors/<id>/frames, header "
                 "<IHHff> = sweep_n, rows, cols, min, max; NaN = missing cell)",
    },
}

__all__ = ["PressureArray", "METADATA"]
