try:
    from devices.si5351.device import Si5351Device, plan_clock, plan_outputs
except ImportError:
    pass  # smbus2 not available — METADATA below must still load

METADATA = {
    "type": "si5351",
    "description": "Si5351A clock generator — up to 3 outputs (CLK0-2) from two "
                   "PLLs, programmed at boot (clock-tree root).",
    "bus": {"kind": "i2c"},
    "optional": ["bus", "address"],
    "valid": {"address": [0x60, 0x61]},   # Si5351A/B-B variants
    "params": ["clk0_hz", "clk1_hz", "clk2_hz"],   # ≤2 distinct frequencies
}

__all__ = ["Si5351Device", "plan_clock", "plan_outputs", "METADATA"]
