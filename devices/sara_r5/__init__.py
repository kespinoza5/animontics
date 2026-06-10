try:
    from devices.sara_r5.device import SaraR5Device
except ImportError:
    pass  # pyserial not available on dev machines — skip gracefully

__all__ = ["SaraR5Device"]
