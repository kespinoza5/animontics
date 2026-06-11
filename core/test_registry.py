"""Unit tests for the sensor registry — registration, creation, error paths."""
from __future__ import annotations

import pytest

from core import registry
from core.models import SensorConfig
from core.sensor_base import SensorBase


class _StubSensor(SensorBase):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    @property
    def latest(self):
        return None
    def is_healthy(self) -> bool:
        return True


@pytest.fixture
def clean_registry(monkeypatch):
    """Run against an isolated registry so tests never pollute the global one."""
    monkeypatch.setattr(registry, "_registry", {})


def test_register_and_create(clean_registry):
    registry.register("stub")(_StubSensor)
    sensor = registry.create(SensorConfig(id="s1", type="stub"))
    assert isinstance(sensor, _StubSensor)
    assert sensor.id == "s1"
    assert registry.registered_types() == ["stub"]


def test_unknown_type_error_names_known_types(clean_registry):
    registry.register("stub")(_StubSensor)
    with pytest.raises(ValueError, match=r"Unknown sensor type 'nope'.*stub"):
        registry.create(SensorConfig(id="x", type="nope"))


def test_real_plugin_tree_registers_on_import():
    """The side-effect import contract node/app.py relies on."""
    import sensors  # noqa: F401
    types = registry.registered_types()
    # Pure-Python sensors must register even on a dev machine without smbus2 etc.
    assert "mq_array" in types
    assert "pressure_array" in types
