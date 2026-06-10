try:
    from sensors.sara_r5_gnss.sensor import SaraR5GnssSensor
except ImportError:
    pass  # pyserial / hardware deps not available on Windows dev machines

#: Hardware constraints and defaults for the fleet tool.
#: Requires a sara_r5 device — no direct connection of its own.
METADATA = {
    "type": "sara_r5_gnss",
    "name": "SARA-R5 GNSS (via LTE modem)",
    "description": (
        "GNSS position, velocity, and fix quality from the u-blox SARA-R5 modem's "
        "integrated GNSS engine. Fed by a sara_r5 device via NMEA push callbacks."
    ),
    "connection": {
        # The physical UART is owned by the sara_r5 device; list its id under
        # `devices:` in the board config instead of specifying a connection here.
        "supported": [],
        "notes": "No direct connection — attach via `devices: [<sara_r5_device_id>]`.",
    },
    "data_keys": {
        "latitude":    "float | None  — decimal degrees, negative = South",
        "longitude":   "float | None  — decimal degrees, negative = West",
        "alt_m":       "float | None  — altitude above mean sea level in metres",
        "fix_quality": "int | None    — 0=none, 1=GPS, 2=DGPS, 4=RTK, 5=float RTK",
        "satellites":  "int | None    — number of satellites used in fix",
        "hdop":        "float | None  — horizontal dilution of precision",
        "speed_kph":   "float | None  — speed over ground in km/h",
        "heading_deg": "float | None  — course over ground in degrees (true north)",
        "utc_time":    "str | None    — ISO-8601 UTC timestamp from GNSS receiver",
        "rmc_valid":   "bool | None   — True when the RMC sentence reports an active fix",
    },
}

__all__ = ["SaraR5GnssSensor", "METADATA"]
