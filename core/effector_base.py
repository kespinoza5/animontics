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

    # NOTE: each effector package's __init__.py declares a module-level
    # METADATA dict (import-safe, like sensors) — the authoring schema `animon
    # deploy` validates board configs against. Field reference: CONTRIBUTING.md.

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


# Concrete effector types live in the effectors/ plugin tree (effectors/pwm,
# effectors/fan_array, effectors/stream_sink, …), auto-discovered like sensors.
