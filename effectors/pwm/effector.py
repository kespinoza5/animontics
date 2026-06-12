from __future__ import annotations

from core.effector_base import EffectorBase, register_effector
from core.mcu_link import CMD_SET_DUTY


@register_effector("pwm")
class PwmEffector(EffectorBase):
    """Generic PWM outputs (LED brightness, unidirectional motor speed, fans).

    Request body: {"levels": {channel: 0.0-1.0}} (or {channel: level}); levels are
    normalized and scaled to the device's 0-255 command. `channel` may be a name
    or an index. `params.min_duty` (0..1) maps a non-zero level into [min_duty, 1]
    so loads with a minimum start point (e.g. small fans) actually move; level 0
    is always fully off.
    """

    effector_type = "pwm"
    lanes = ("request",)
    SPEC = {
        "description": "Generic PWM duty levels through an MCU device (CMD_SET_DUTY).",
        "backends": {"mcu": ["device"]},
        "default_backend": "mcu",
        "params": ["min_duty"],
    }

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["value"] = "0.0-1.0"
        d["min_duty"] = self._default_min_duty
        return d

    @property
    def _default_min_duty(self) -> float:
        return max(0.0, min(1.0, float(self.config.params.get("min_duty", 0.0))))

    def _min_duty_for(self, channel_name: str) -> float:
        """Per-channel minimum (subclasses can override, e.g. per-fan)."""
        return self._default_min_duty

    def _to_duty(self, level: float, channel_name: str) -> int:
        if level <= 0.0:
            return 0
        lo = self._min_duty_for(channel_name)
        return max(0, min(255, round((lo + (1.0 - lo) * min(1.0, level)) * 255)))

    def handle_request(self, payload: dict) -> dict:
        levels = payload.get("levels", payload)
        if not isinstance(levels, dict) or not levels:
            return {"error": "expected {'levels': {channel: 0.0-1.0}}"}
        results: dict[str, str] = {}
        for key, level in levels.items():
            ch = self._channel(key)
            if ch is None:
                results[str(key)] = "unknown channel"
                continue
            ok = self._device is not None and self._device.send_command(
                CMD_SET_DUTY, [ch.index, self._to_duty(float(level), ch.name)]
            )
            self._state[ch.name] = round(float(level), 4)
            results[ch.name] = "ok" if ok else "link down"
        return {"set": results}
