"""Unit tests for servo_feedback — counts→degrees calibration (no hardware)."""
from __future__ import annotations

from core.mcu_link import FrameStream, encode
from core.models import SensorChannel, SensorConfig
from sensors.servo_feedback.sensor import ServoFeedback


def _sensor(channels):
    return ServoFeedback("neck", SensorConfig(id="neck", type="servo_feedback",
                                              channels=channels))


def _frame(samples, seq=0):
    return FrameStream().feed(encode(samples, seq=seq))[0]


def test_counts_to_degrees_with_clamp():
    s = _sensor([
        SensorChannel(index=0, signal="yaw", device="cervical",
                      calibration={"type": "servo_pot", "counts_min": 1000,
                                   "counts_max": 21000, "deg_min": 0, "deg_max": 180}),
        SensorChannel(index=1, signal="pitch", device="cervical",
                      calibration={"type": "servo_pot", "counts_min": 0,
                                   "counts_max": 20000, "deg_min": 30, "deg_max": 150}),
        SensorChannel(index=2, signal="aux", device="cervical"),       # raw only
    ])
    r = s.ingest("cervical", _frame([11000, 30000, 42]))
    assert r.data["raw"] == {"yaw": 11000, "pitch": 30000, "aux": 42}
    assert r.data["deg"]["yaw"] == 90.0
    assert r.data["deg"]["pitch"] == 150.0          # over-range → clamped to deg_max
    assert "aux" not in r.data["deg"]               # uncalibrated stays raw-only


def test_multi_device_ears_and_neck():
    s = _sensor([
        SensorChannel(index=0, signal="yaw", device="cervical",
                      calibration={"type": "servo_pot", "counts_min": 0,
                                   "counts_max": 10000, "deg_min": 0, "deg_max": 180}),
        SensorChannel(index=0, signal="ear_left", device="head_adc",
                      calibration={"type": "servo_pot", "counts_min": 0,
                                   "counts_max": 26400, "deg_min": 0, "deg_max": 180}),
    ])
    s.ingest("cervical", _frame([5000]))
    r = s.ingest("head_adc", _frame([13200]))
    assert r.data["deg"] == {"yaw": 90.0, "ear_left": 90.0}
