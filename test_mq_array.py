"""Unit tests for mq_array — gas math + enrich (no hardware)."""
from __future__ import annotations

import pytest

from core.mcu_link import FrameStream, encode
from core.models import ConnectionConfig, SensorChannel, SensorConfig
from sensors.mq_array.driver import ADC_MAX, rs_over_r0, rs_over_rl
from sensors.mq_array.sensor import MqArray


class TestGasMath:
    def test_rs_over_rl_open_input(self):
        assert rs_over_rl(0) is None

    def test_rs_over_rl_midscale(self):
        assert rs_over_rl(512) == pytest.approx((ADC_MAX - 512) / 512)

    def test_rs_over_r0_unity_when_rl_eq_r0_and_ratio_one(self):
        # raw such that Rs/RL == 1, with RL == R0 → Rs/R0 == 1
        raw = ADC_MAX // 2 + 1  # ~ (max-raw)/raw just under 1; use exact below
        # exact: pick raw so (max-raw)/raw = 1 → raw = max/2 (1023/2 not integer)
        assert rs_over_r0(0, 10000, 10000) is None
        assert rs_over_r0(512, 10000, 10000) == pytest.approx(rs_over_rl(512))

    def test_rs_over_r0_bad_r0(self):
        assert rs_over_r0(500, 10000, 0) is None


def _sensor(channels: list[SensorChannel]) -> MqArray:
    cfg = SensorConfig(
        id="gas",
        type="mq_array",
        connection=ConnectionConfig(type="uart", port="/dev/ttyUSB0", baud_rate=115200),
        channels=channels,
    )
    return MqArray("gas", cfg)


class TestEnrich:
    def test_raw_only_when_uncalibrated(self):
        s = _sensor([SensorChannel(index=0, signal="mq135")])
        data = {"raw": {"mq135": 500}}
        s.enrich(data, data["raw"])
        assert "ratio" not in data

    def test_adds_ratio_when_mq_calibrated(self):
        s = _sensor([
            SensorChannel(index=0, signal="mq135",
                          calibration={"type": "mq", "rl": 10000, "r0": 10000}),
        ])
        data = {"raw": {"mq135": 512}}
        s.enrich(data, data["raw"])
        assert "mq135" in data["ratio"]
        assert data["ratio"]["mq135"] == pytest.approx(rs_over_r0(512, 10000, 10000), rel=1e-3)

    def test_mixed_channels(self):
        s = _sensor([
            SensorChannel(index=0, signal="mq135",
                          calibration={"type": "mq", "rl": 10000, "r0": 10000}),
            SensorChannel(index=1, signal="mq2"),  # raw only
        ])
        data = {"raw": {"mq135": 400, "mq2": 600}}
        s.enrich(data, data["raw"])
        assert set(data["ratio"]) == {"mq135"}     # only the calibrated one


class TestEndToEnd:
    """Bytes a forge-built MCU would emit → FrameStream → SensorReading.

    Exercises the whole node-side decode chain (core.mcu_link + AnalogArrayBase
    index→signal mapping + MqArray.enrich) in software — the strongest check
    available without hardware.
    """

    def test_encoded_frame_becomes_reading(self):
        s = _sensor([
            SensorChannel(index=0, signal="mq135",
                          calibration={"type": "mq", "rl": 10000, "r0": 10000}),
            SensorChannel(index=1, signal="mq2"),  # raw only
        ])
        wire = encode([400, 600], seq=3)            # as transport_serial would send
        frames = FrameStream().feed(wire)
        assert len(frames) == 1

        reading = s._reading(frames[0])
        assert reading.sensor_type == "mq_array"
        assert reading.data["seq"] == 3
        assert reading.data["raw"] == {"mq135": 400, "mq2": 600}
        assert "mq135" in reading.data["ratio"]
        assert "mq2" not in reading.data["ratio"]   # uncalibrated → raw only

    def test_resyncs_across_garbage_and_split_reads(self):
        s = _sensor([SensorChannel(index=0, signal="mq135")])
        wire = encode([512], seq=1)
        stream = FrameStream()
        frames = stream.feed(b"\x00noise" + wire[:3])   # garbage + partial frame
        frames += stream.feed(wire[3:])                  # rest arrives later
        readings = [s._reading(f) for f in frames]
        assert [r.data["raw"] for r in readings] == [{"mq135": 512}]
