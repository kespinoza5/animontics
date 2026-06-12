try:
    from sensors.sara_r5_lte.sensor import SaraR5LteSensor
except ImportError:
    pass  # pyserial / hardware deps not available on Windows dev machines

#: Hardware constraints and defaults for the fleet tool.
METADATA = {
    "type": "sara_r5_lte",
    "name": "SARA-R5 LTE-M Signal Quality",
    "description": (
        "LTE-M/NB-IoT signal quality (RSRP, RSRQ, RSSI), network registration "
        "state, and operator from the u-blox SARA-R5 modem. Polled via AT commands "
        "through a sara_r5 device every 30 seconds."
    ),
    "connection": {
        "supported": [],
        "defaults": {},
        "valid": {},
        "notes": "No direct connection — attach via `devices: [<sara_r5_device_id>]`.",
    },
    "data_keys": {
        "rsrp_dbm":          "float | None  — LTE reference signal received power (dBm)",
        "rsrq_db":           "float | None  — LTE reference signal received quality (dB)",
        "rssi_dbm":          "float | None  — received signal strength indicator (dBm)",
        "registration_state": "str | None   — not_registered | registered_home | searching | denied | registered_roaming",
        "rat":               "str | None    — radio access technology: LTE | LTE_M1 | NB_IoT | ...",
        "operator":          "str | None    — network operator name",
        "band":              "str | None    — active radio band / RAT from COPS response",
    },
}

__all__ = ["SaraR5LteSensor", "METADATA"]
