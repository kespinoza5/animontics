"""Effectors — efferent outputs (motion, light, sound), the dual of sensors.

Not "actuators": this tier covers fans/motors/servos AND LEDs, speakers, etc.
Each effector *type* defines its own drive interface (no universal verb) over one
or both lanes:

  • request lane — an occasional value that holds (fan level, LED colour, servo
    target). Driven by POST /effectors/{id}; handled by `handle_request`.
  • stream  lane — a continuous flow (speaker audio, LED-strip animation). Driven
    by WS /effectors/{id}/stream; handled by `feed`.

An effector writes through a device (it never owns a transport) or a future
SBC-direct backend. Channels carry a name (API/UX) and an index (the wire/command
channel). Effectors are created at node startup and held on app.state.effectors.
"""
from __future__ import annotations

import logging
from abc import ABC
from typing import TYPE_CHECKING, Any

from core.mcu_link import CMD_SET_DUTY

if TYPE_CHECKING:
    from core.device import Device
    from core.models import EffectorChannel, EffectorConfig

log = logging.getLogger(__name__)

_registry: dict[str, type["EffectorBase"]] = {}


def register_effector(effector_type: str):
    def decorator(cls: type["EffectorBase"]) -> type["EffectorBase"]:
        cls.effector_type = effector_type
        _registry[effector_type] = cls
        return cls
    return decorator


def create_effector(config: "EffectorConfig") -> "EffectorBase":
    cls = _registry.get(config.type)
    if cls is None:
        raise ValueError(
            f"Unknown effector type '{config.type}'. Known: {sorted(_registry)}."
        )
    return cls(config.id, config)


class EffectorBase(ABC):
    """Base for output devices. Subclasses set `effector_type`/`lanes` and
    implement the lane handler(s) their type uses."""

    effector_type: str = "effector"
    lanes: tuple[str, ...] = ("request",)     # "request" and/or "stream"

    def __init__(self, effector_id: str, config: "EffectorConfig") -> None:
        self.id = effector_id
        self.config = config
        self.channels = config.channels
        self._device: "Device | None" = None
        self._state: dict[str, Any] = {}      # last-commanded value per channel name

    # ── Binding ───────────────────────────────────────────────────────────────

    def attach_devices(self, devices: dict[str, "Device"]) -> None:
        """Bind the backend device (if this effector drives one)."""
        dev_id = self.config.backend.get("device")
        if dev_id is not None:
            if dev_id not in devices:
                raise ValueError(f"effector '{self.id}': unknown device '{dev_id}'")
            self._device = devices[dev_id]

    def _channel(self, key) -> "EffectorChannel | None":
        for ch in self.channels:
            if ch.name == key or ch.index == key:
                return ch
        return None

    # ── Introspection ─────────────────────────────────────────────────────────

    def descriptor(self) -> dict:
        """Type + channels + lanes + value domain — lets a UI render the right control."""
        return {
            "type": self.effector_type,
            "lanes": list(self.lanes),
            "channels": [{"name": c.name, "index": c.index} for c in self.channels],
        }

    def state(self) -> dict:
        return dict(self._state)

    # ── Lane handlers (type-defined; override the ones your type supports) ─────

    def handle_request(self, payload: dict) -> dict:
        raise NotImplementedError(f"{self.effector_type} has no request lane")

    def feed(self, chunk: bytes) -> None:
        raise NotImplementedError(f"{self.effector_type} has no stream lane")

    # ── Lifecycle (optional) ──────────────────────────────────────────────────

    def start(self) -> None: ...
    def stop(self) -> None: ...


@register_effector("pwm")
class PwmEffector(EffectorBase):
    """PWM outputs (fans, LED brightness, unidirectional motor speed).

    Request body: {"levels": {channel: 0.0-1.0}} (or {channel: level}); levels are
    normalized and scaled to the device's 0-255 command. channel may be a name or
    an index.
    """

    effector_type = "pwm"
    lanes = ("request",)

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["value"] = "0.0-1.0"
        d["min_duty"] = self._min_duty
        return d

    @property
    def _min_duty(self) -> float:
        """Lowest non-zero output (0..1). A non-zero level maps into [min_duty, 1];
        level 0 is always fully off. Lets tiny/high-rpm fans actually start."""
        return max(0.0, min(1.0, float(self.config.params.get("min_duty", 0.0))))

    def _to_duty(self, level: float) -> int:
        if level <= 0.0:
            return 0                                  # off
        lo = self._min_duty
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
                CMD_SET_DUTY, [ch.index, self._to_duty(float(level))]
            )
            self._state[ch.name] = round(float(level), 4)
            results[ch.name] = "ok" if ok else "link down"
        return {"set": results}


@register_effector("stream_sink")
class StreamSink(EffectorBase):
    """Reference stream-lane effector (no hardware) — records what it receives.

    Proves the continuous-flow lane end to end (WS → feed) and is the template a
    real speaker / LED-strip effector follows.
    """

    effector_type = "stream_sink"
    lanes = ("stream",)

    def __init__(self, effector_id: str, config: "EffectorConfig") -> None:
        super().__init__(effector_id, config)
        self._bytes = 0
        self._last_len = 0

    def feed(self, chunk: bytes) -> None:
        self._bytes += len(chunk)
        self._last_len = len(chunk)

    def state(self) -> dict:
        return {"bytes_received": self._bytes, "last_chunk": self._last_len}
