"""Unit tests for radar_motion — adaptive baseline + threshold (no hardware)."""
from __future__ import annotations

from core.mcu_link import FrameStream, encode
from core.models import SensorChannel, SensorConfig
from sensors.radar_motion.sensor import RadarMotion


def _sensor(params=None):
    return RadarMotion("radar", SensorConfig(
        id="radar", type="radar_motion", params=params or {"threshold": 500},
        channels=[SensorChannel(index=0, signal="fore", device="adc")],
    ))


def _frame(samples, seq=0):
    return FrameStream().feed(encode(samples, seq=seq))[0]


def test_first_sample_seeds_baseline_no_motion():
    s = _sensor()
    r = s.ingest("adc", _frame([12000]))
    assert r.data["level"]["fore"] == 0.0
    assert r.data["motion"]["fore"] is False


def test_deviation_trips_motion_and_baseline_holds():
    s = _sensor()
    s.ingest("adc", _frame([12000]))
    r = s.ingest("adc", _frame([13000]))            # 1000 counts of Doppler
    assert r.data["motion"]["fore"] is True
    assert r.data["level"]["fore"] == 1000.0
    # baseline must NOT have absorbed the moving target
    r = s.ingest("adc", _frame([12000]))
    assert r.data["motion"]["fore"] is False


def test_baseline_tracks_slow_drift():
    s = _sensor({"threshold": 500, "baseline_alpha": 0.5})
    s.ingest("adc", _frame([12000]))
    for v in (12100, 12200, 12300):                 # slow drift, under threshold
        r = s.ingest("adc", _frame([v]))
    assert r.data["motion"]["fore"] is False
    assert s._baseline["fore"] > 12000              # baseline followed the drift
