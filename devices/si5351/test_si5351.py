"""Unit tests for the Si5351 frequency planner (no hardware)."""
from __future__ import annotations

import pytest

from devices.si5351.device import _DENOM, _msynth_params, plan_clock


def _resolved_hz(target, xtal=25_000_000):
    fb_int, fb_num, fb_denom, out_div = plan_clock(target, xtal)
    return xtal * (fb_int + fb_num / fb_denom) / out_div


@pytest.mark.parametrize("scki", [
    12_288_000,     # 256 × 48 kHz — the PCM1808 plan of record
    11_289_600,     # 256 × 44.1 kHz
    24_576_000,     # 512 × 48 kHz
])
def test_audio_clocks_hit_within_1hz(scki):
    assert abs(_resolved_hz(scki) - scki) < 1.0


def test_divider_is_even_and_pll_in_range():
    fb_int, fb_num, fb_denom, out_div = plan_clock(12_288_000)
    assert out_div % 2 == 0
    assert 600e6 <= 12_288_000 * out_div <= 900e6
    assert fb_denom == _DENOM


def test_out_of_range_raises():
    with pytest.raises(ValueError):
        plan_clock(0)
    with pytest.raises(ValueError):
        plan_clock(500_000_000)         # above any reachable output


def test_msynth_encoding_integer_divider():
    # integer divider d: p1 = 128*d - 512, p2 = 0, p3 = 1
    regs = _msynth_params(64, 0, 1)
    p1 = (regs[2] << 16) | (regs[3] << 8) | regs[4]
    assert p1 == 128 * 64 - 512
    assert regs[6] == 0 and regs[7] == 0          # p2 = 0
    assert regs[1] == 1                           # p3 low byte = 1
