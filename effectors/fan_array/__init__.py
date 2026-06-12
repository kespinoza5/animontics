try:
    from effectors.fan_array.effector import FanArray
except ImportError:
    pass  # hardware deps unavailable — METADATA below must still load

METADATA = {
    "type": "fan_array",
    "description": "Named fans over the request lane — per-fan min_duty atop pwm.",
    "backends": {"mcu": ["device"]},
    "default_backend": "mcu",
    "mcu_command": "set_duty",
    "params": ["min_duty", "per_fan"],
}

__all__ = ["FanArray", "METADATA"]
