"""Unit tests for audio_in — PCM block math + frame header (no hardware)."""
from __future__ import annotations

import math
import struct

from sensors.audio_in.driver import block_stats


def _pcm(*frames):
    """Interleaved S16_LE from per-frame tuples."""
    flat = [s for frame in frames for s in frame]
    return struct.pack(f"<{len(flat)}h", *flat)


def test_silence_is_minus_120_dbfs():
    stats = block_stats(_pcm((0, 0), (0, 0)), channels=2)
    assert stats[0]["rms"] == 0.0 and stats[0]["dbfs"] == -120.0
    assert stats[1]["peak"] == 0.0


def test_full_scale_square_wave():
    pcm = _pcm((32767, -32768), (-32768, 32767), (32767, -32768), (-32768, 32767))
    stats = block_stats(pcm, channels=2)
    for ch in stats:
        assert math.isclose(ch["rms"], 1.0, rel_tol=0.001)
        assert ch["peak"] == 1.0
        assert abs(ch["dbfs"]) < 0.1


def test_channels_are_independent():
    pcm = _pcm((16384, 0), (-16384, 0), (16384, 0), (-16384, 0))
    left, right = block_stats(pcm, channels=2)
    assert math.isclose(left["rms"], 0.5, rel_tol=0.001)
    assert right["rms"] == 0.0


def test_partial_trailing_frame_is_ignored():
    pcm = _pcm((1000, 1000)) + b"\x01"            # one stray byte
    stats = block_stats(pcm, channels=2)
    assert len(stats) == 2 and stats[0]["peak"] > 0
