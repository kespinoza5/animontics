try:
    from devices.si5351.device import Si5351Device, plan_clock
except ImportError:
    pass  # smbus2 not available — METADATA below must still load

METADATA = {
    "type": "si5351",
    "description": "Si5351 clock generator — programs CLK0 at boot (clock-tree root).",
    "optional": ["bus", "address"],
    "params": ["clk0_hz"],
}

__all__ = ["Si5351Device", "plan_clock", "METADATA"]
