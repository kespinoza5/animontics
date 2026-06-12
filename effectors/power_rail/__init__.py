try:
    from effectors.power_rail.effector import PowerRail
except ImportError:
    pass  # hardware deps unavailable — METADATA below must still load

METADATA = {
    "type": "power_rail",
    "description": "Switched power rail — gates member devices (gated ≠ failed).",
    "backends": {"gpio": ["line"], "mcu": ["device"]},
    "default_backend": "gpio",
    "mcu_command": "set_gpio",
    # anything that isn't "off" switches on — a typo'd "offf" would silently
    # energize the rail, so the value set is enforced at deploy.
    "valid": {"initial": ["on", "off"]},
    "params": ["initial", "members"],
}

__all__ = ["PowerRail", "METADATA"]
