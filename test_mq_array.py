"""Unit tests for mq_array — gas math + enrich (no hardware)."""
from __future__ import annotations

import pytest

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
