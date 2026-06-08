"""Unit test for fan_tach — device frame of RPM → reading (no hardware)."""
from __future__ import annotations

from core.mcu_link import FrameStream, encode
from core.models import SensorChannel, SensorConfig
from sensors.fan_tach.sensor import FanTach


def test_streams_rpm():
    s = FanTach("rpm", SensorConfig(id="rpm", type="fan_tach", channels=[
        SensorChannel(index=0, signal="intake", device="lxiao"),
        SensorChannel(index=1, signal="exhaust", device="lxiao"),
    ]))
    frame = FrameStream().feed(encode([5400, 4980], seq=2))[0]
    r = s.ingest("lxiao", frame)
    assert r.sensor_type == "fan_tach"
    assert r.data["raw"] == {"intake": 5400, "exhaust": 4980}
    assert r.data["rpm"] == {"intake": 5400, "exhaust": 4980}   # alias of raw
