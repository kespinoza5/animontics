try:
    from devices.ads1115.device import Ads1115Device
except ImportError:
    pass  # smbus2 not available — METADATA below must still load

METADATA = {
    "type": "ads1115",
    "description": "ADS1115 4-channel I2C ADC — pull device, serialized single-shot reads.",
    "bus": {"kind": "i2c"},
    "optional": ["bus", "address"],
    "valid": {"address": [0x48, 0x49, 0x4A, 0x4B],     # the four ADDR strap options
              "data_rate": [8, 16, 32, 64, 128, 250, 475, 860]},   # the chip's DR field
    "params": ["data_rate"],
}

__all__ = ["Ads1115Device", "METADATA"]
