"""Unit tests for mq_array — gas math, enrich, and device-fed compose (no hardware)."""
from __future__ import annotations

import pytest

from core.mcu_link import FrameStream, encode
from core.models import SensorChannel, SensorConfig
from sensors.mq_array.driver import ADC_MAX, rs_over_r0, rs_over_rl
from sensors.mq_array.sensor import MqArray


class TestGasMath:
    def test_rs_over_rl_open_input(self):
        assert rs_over_rl(0) is None

    def test_rs_over_rl_midscale(self):
        assert rs_over_rl(512) == pytest.approx((ADC_MAX - 512) / 512)

    def test_rs_over_r0_matches_ratio_when_rl_eq_r0(self):
        assert rs_over_r0(0, 10000, 10000) is None
        assert rs_over_r0(512, 10000, 10000) == pytest.approx(rs_over_rl(512))

    def test_rs_over_r0_bad_r0(self):
        assert rs_over_r0(500, 10000, 0) is None


def _sensor(channels: list[SensorChannel]) -> MqArray:
    return MqArray("gas", SensorConfig(id="gas", type="mq_array", channels=channels))


class TestEnrich:
    def test_raw_only_when_uncalibrated(self):
        s = _sensor([SensorChannel(index=0, signal="mq135", device="larduino")])
        data = {"raw": {"mq135": 500}}
        s.enrich(data, data["raw"])
        assert "ratio" not in data

    def test_adds_ratio_when_mq_calibrated(self):
        s = _sensor([
            SensorChannel(index=0, signal="mq135", device="larduino",
                          calibration={"type": "mq", "rl": 10000, "r0": 10000}),
        ])
        data = {"raw": {"mq135": 512}}
        s.enrich(data, data["raw"])
        assert data["ratio"]["mq135"] == pytest.approx(rs_over_r0(512, 10000, 10000), rel=1e-3)

    def test_mixed_channels(self):
        s = _sensor([
            SensorChannel(index=0, signal="mq135", device="larduino",
                          calibration={"type": "mq", "rl": 10000, "r0": 10000}),
            SensorChannel(index=1, signal="mq2", device="larduino"),
        ])
        data = {"raw": {"mq135": 400, "mq2": 600}}
        s.enrich(data, data["raw"])
        assert set(data["ratio"]) == {"mq135"}


class TestDeviceFedCompose:
    """A frame from a device → ingest → composed reading (the runtime path)."""

    def test_single_device_frame_becomes_reading(self):
        s = _sensor([
            SensorChannel(index=0, signal="mq135", device="larduino",
                          calibration={"type": "mq", "rl": 10000, "r0": 10000}),
            SensorChannel(index=1, signal="mq2", device="larduino"),
        ])
        frame = FrameStream().feed(encode([400, 600], seq=3))[0]
        reading = s.ingest("larduino", frame)
        assert reading.sensor_type == "mq_array"
        assert reading.data["seq"] == 3
        assert reading.data["raw"] == {"mq135": 400, "mq2": 600}
        assert "mq135" in reading.data["ratio"] and "mq2" not in reading.data["ratio"]
        assert s.latest is reading

    def test_aggregates_across_devices(self):
        # one logical sensor spanning two devices (the cranial-pressure pattern)
        s = _sensor([
            SensorChannel(index=0, signal="a0", device="dev0"),
            SensorChannel(index=1, signal="a1", device="dev0"),
            SensorChannel(index=0, signal="b0", device="dev1"),
        ])
        s.ingest("dev0", FrameStream().feed(encode([10, 20], seq=1))[0])
        reading = s.ingest("dev1", FrameStream().feed(encode([30], seq=2))[0])
        assert reading.data["raw"] == {"a0": 10, "a1": 20, "b0": 30}  # latest from both
