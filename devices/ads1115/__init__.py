try:
    from devices.ads1115.device import Ads1115Device
except ImportError:
    pass  # smbus2 not available on dev machines — skip gracefully

__all__ = ["Ads1115Device"]
