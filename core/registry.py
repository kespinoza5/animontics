"""Sensor plugin registry. Maps type-key strings to SensorBase subclasses."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.sensor_base import SensorBase
    from core.models import SensorConfig

_registry: dict[str, type["SensorBase"]] = {}


def register(sensor_type: str):
    """
    Class decorator that registers a SensorBase subclass under a type key.

    Usage:
        @register("tf_mini")
        class TFminiSensor(SensorBase):
            ...

    The key must match the `type` field used in config.yaml sensor entries.
    """
    def decorator(cls: type["SensorBase"]) -> type["SensorBase"]:
        _registry[sensor_type] = cls
        return cls
    return decorator


def create(config: "SensorConfig") -> "SensorBase":
    """Instantiate a sensor from its config. Raises ValueError for unknown types."""
    cls = _registry.get(config.type)
    if cls is None:
        known = sorted(_registry)
        raise ValueError(
            f"Unknown sensor type '{config.type}'. "
            f"Known types: {known}. "
            f"Is the sensor package present on this board?"
        )
    return cls(config.id, config)


def registered_types() -> list[str]:
    """Return all currently registered sensor type keys."""
    return sorted(_registry)
