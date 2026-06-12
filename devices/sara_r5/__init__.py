try:
    from devices.sara_r5.device import SaraR5Device
except ImportError:
    pass  # pyserial not available — METADATA below must still load

METADATA = {
    "type": "sara_r5",
    "description": "u-blox SARA-R5 modem — NMEA push + AT poll over one UART.",
    "bus": {"kind": "uart"},
    "required": ["port"],
    "optional": ["baud"],
    "valid": {"baud": [115200]},   # the rate the driver's AT init assumes
    "params": ["init", "power_on_delay_s", "reset_settle_s",
               "power_line", "reset_line"],
}

__all__ = ["SaraR5Device", "METADATA"]
