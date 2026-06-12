"""Devices — shared peripherals that sensors read through and effectors write through.

A device owns a transport that is shared across directions or across several
logical sensors/effectors, so neither a sensor nor an effector may own it (an MCU
serial link, an ADS1115 chip, a SARA-R5 modem).

This module holds only the **base class + registry + factory**. Concrete device
kinds live in the `devices/` plugin tree (`devices/mcu_serial`, `devices/ads1115`,
`devices/sara_r5`, …), auto-discovered exactly like `sensors/`, `effectors/`, and
`policies/`. `node/app.py` does `import devices` for the side-effect discovery, so
each `@register_device` fires and populates the registry below.

Devices are created from config at node startup and held on `app.state.devices`;
sensors/effectors bind to them by id.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import DeviceConfig

log = logging.getLogger(__name__)

_registry: dict[str, type["Device"]] = {}


def register_device(kind: str):
    """Class decorator registering a Device subclass under a `kind` key."""
    def decorator(cls: type["Device"]) -> type["Device"]:
        cls.kind = kind
        _registry[kind] = cls
        return cls
    return decorator


def create_device(config: "DeviceConfig") -> "Device":
    """Instantiate a device from its config. Raises ValueError for unknown kinds.

    The kind must be registered, which happens when its package under `devices/`
    is imported. If a kind is missing, check that `import devices` ran and the
    package's hardware deps are installed (failed imports are skipped, not fatal).
    """
    cls = _registry.get(config.kind)
    if cls is None:
        raise ValueError(
            f"Unknown device kind '{config.kind}'. Known: {sorted(_registry)}. "
            f"Is the device package present on this board?"
        )
    return cls(config.id, config)


def registered_kinds() -> list[str]:
    """Return all currently registered device kind keys."""
    return sorted(_registry)


class Device(ABC):
    """Base class for shared peripherals.

    Subclasses decorate with `@register_device("kind")` and implement the
    lifecycle. Push devices (e.g. an MCU link, a modem's NMEA stream) fan decoded
    data to `subscribe*()` callbacks; pull devices (e.g. an ADS1115) expose a read
    method. Either way the device owns the transport — sensors and effectors bind
    to it by id and never open the port themselves.
    """

    kind: str = ""

    # NOTE: each device package's __init__.py declares a module-level METADATA
    # dict (import-safe, like sensors) — the authoring schema `animon deploy`
    # validates board configs against. Field reference: CONTRIBUTING.md →
    # "Adding a device, effector, or policy".

    def __init__(self, device_id: str, config: "DeviceConfig") -> None:
        self.id = device_id
        self.config = config

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def is_healthy(self) -> bool: ...


# Concrete device kinds live in the devices/ plugin tree (devices/mcu_serial,
# devices/ads1115, devices/sara_r5, …), auto-discovered like sensors.
