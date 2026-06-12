try:
    from devices.mcu_serial.device import McuSerialDevice
except ImportError:
    pass  # pyserial not available — METADATA below must still load

METADATA = {
    "type": "mcu_serial",
    "description": "Serial link to an MCU — decodes sample frames, sends command frames.",
    "bus": {"kind": "usb_cdc"},   # USB CDC — no SBC header pins to validate
    "required": ["port"],
    "optional": ["baud"],
    "params": [],
}

__all__ = ["McuSerialDevice", "METADATA"]
