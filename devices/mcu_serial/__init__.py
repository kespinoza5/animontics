try:
    from devices.mcu_serial.device import McuSerialDevice
except ImportError:
    pass  # pyserial not available on dev machines — skip gracefully

__all__ = ["McuSerialDevice"]
