try:
    from sensors.board_temp.sensor import BoardTemp
except ImportError:
    pass  # no hardware deps, but keep the guard pattern uniform

#: SBC-native sensor — no connection, no device. In-tree (not a submodule): it is
#: trivial and has no independent lifecycle.
METADATA = {
    "type": "board_temp",
    "name": "SBC board/CPU temperature (sysfs thermal zones)",
    "description": "Reads Linux /sys/class/thermal zones — no external hardware.",
    "connection": {
        "supported": [],          # connectionless
        "defaults": {},
        "valid": {},
    },
    "data_keys": {
        "cpu_c":   "float — primary (zone0) temperature in °C",
        "zone0_c": "float — thermal zone 0 temperature in °C",
        "zoneN_c": "float — additional thermal zones, if present",
    },
}

__all__ = ["BoardTemp", "METADATA"]
