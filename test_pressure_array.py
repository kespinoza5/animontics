"""Unit tests for pressure_array — transfer math + multi-device compose (no hardware)."""
from __future__ import annotations

import pytest

from core.mcu_link import FrameStream, encode
from core.models import SensorChannel, SensorConfig
from sensors.pressure_array.driver import to_kpa
from sensors.pressure_array.sensor import PressureArray


def test_to_kpa_linear():
    assert to_kpa(1000, 0.1, -5.0) == pytest.approx(95.0)


def _sensor(channels):
    return PressureArray("cp", SensorConfig(id="cp", type="pressure_array", channels=channels))


def test_aggregates_across_devices_with_kpa():
    s = _sensor([
        SensorChannel(index=0, signal="cp_00", device="press0",
                      calibration={"type": "linear", "scale": 0.1, "offset": 0.0}),
        SensorChannel(index=1, signal="cp_01", device="press0"),                 # raw only
        SensorChannel(index=0, signal="cp_16", device="press1",
                      calibration={"type": "linear", "scale": 0.2, "offset": 0.0}),
    ])
    s.ingest("press0", FrameStream().feed(encode([300, 400], seq=1))[0])
    reading = s.ingest("press1", FrameStream().feed(encode([500], seq=2))[0])
    assert reading.data["raw"] == {"cp_00": 300, "cp_01": 400, "cp_16": 500}
    assert reading.data["kpa"] == {"cp_00": 30.0, "cp_16": 100.0}   # only calibrated channels
