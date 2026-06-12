try:
    from effectors.pwm.effector import PwmEffector
except ImportError:
    pass  # hardware deps unavailable — METADATA below must still load

METADATA = {
    "type": "pwm",
    "description": "Generic PWM duty levels through an MCU device (CMD_SET_DUTY).",
    "backends": {"mcu": ["device"]},
    "default_backend": "mcu",
    "mcu_command": "set_duty",
    "valid": {"min_duty": {"min": 0, "max": 1}},
    "params": ["min_duty"],
}

__all__ = ["PwmEffector", "METADATA"]
