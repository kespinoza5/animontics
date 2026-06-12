try:
    from devices.ads1115.device import Ads1115Device
except ImportError:
    pass  # smbus2 not available — METADATA below must still load

METADATA = {
    "type": "ads1115",
    "description": "ADS1115 4-channel I2C ADC — pull device, serialized single-shot reads.",
    "optional": ["bus", "address"],
    "params": [],
}

__all__ = ["Ads1115Device", "METADATA"]
