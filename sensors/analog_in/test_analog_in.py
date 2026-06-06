"""Unit tests for analog_in — per-channel poll + calibration (no hardware)."""
from __future__ import annotations

from core.models import SensorChannel, SensorConfig
from sensors.analog_in.sensor import AnalogIn


class FakeAds:
    def read_channel(self, channel, gain=1):
        return {0: 1000, 1: 2000}.get(channel)


def _sensor(channels):
    return AnalogIn("ai", SensorConfig(id="ai", type="analog_in", channels=channels))


def test_read_once_raw_and_linear():
    s = _sensor([
        SensorChannel(index=0, signal="batt_v", device="adc",
                      calibration={"type": "linear", "scale": 0.001, "offset": 0.0}),
        SensorChannel(index=1, signal="current", device="adc"),     # raw only
    ])
    s.attach_devices({"adc": FakeAds()})
    r = s._read_once()
    assert r.data["raw"] == {"batt_v": 1000, "current": 2000}
    assert r.data["batt_v"] == 1.0          # 1000 * 0.001
    assert "current" not in r.data          # uncalibrated → raw lane only


def test_read_once_none_without_device():
    s = _sensor([SensorChannel(index=0, signal="x", device="adc")])
    assert s._read_once() is None           # nothing bound → nothing read
