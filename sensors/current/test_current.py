"""Unit tests for the current sensor — counts→amps calibration (no hardware)."""
from __future__ import annotations

from core.mcu_link import FrameStream, encode
from core.models import SensorChannel, SensorConfig
from sensors.current.sensor import CurrentSensor


def _frame(samples, seq=0):
    return FrameStream().feed(encode(samples, seq=seq))[0]


def test_acs712_signed_amps():
    s = CurrentSensor("rail", SensorConfig(id="rail", type="current", channels=[
        SensorChannel(index=0, signal="servo_rail", device="adc",
                      calibration={"type": "acs712", "zero_counts": 13300,
                                   "counts_per_amp": 351}),
        SensorChannel(index=1, signal="aux", device="adc"),        # raw only
    ]))
    r = s.ingest("adc", _frame([13300 + 351 * 2, 100]))
    assert r.data["amps"]["servo_rail"] == 2.0
    assert "aux" not in r.data.get("amps", {})
    r = s.ingest("adc", _frame([13300 - 351, 100]))
    assert r.data["amps"]["servo_rail"] == -1.0                    # reverse flow is signed


def test_zero_counts_per_amp_never_divides_by_zero():
    s = CurrentSensor("rail", SensorConfig(id="rail", type="current", channels=[
        SensorChannel(index=0, signal="x", device="adc",
                      calibration={"type": "acs712", "zero_counts": 0,
                                   "counts_per_amp": 0}),
    ]))
    assert s.ingest("adc", _frame([42])).data["amps"]["x"] == 42.0
