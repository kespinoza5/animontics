try:
    from effectors.servo.effector import ServoEffector
except ImportError:
    pass  # hardware deps unavailable — METADATA below must still load

METADATA = {
    "type": "servo",
    "description": "Hobby servos by angle/µs — mcu (CMD_SET_US) or sbc_pwm backend.",
    "backends": {"mcu": ["device"], "sbc_pwm": []},
    "default_backend": "mcu",
    "mcu_command": "set_us",
    "params": ["freq_hz", "min_us", "max_us", "deg_min", "deg_max",
               "trim_deg", "invert", "per_channel"],
}

__all__ = ["ServoEffector", "METADATA"]
