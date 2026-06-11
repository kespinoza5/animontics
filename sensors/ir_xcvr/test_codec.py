"""
Unit tests for sensors.ir_xcvr.codec.

Run with: pytest sensors/ir_xcvr/test_codec.py -v
No hardware required.
"""

from __future__ import annotations

import pytest

from sensors.ir_xcvr.codec import (
    DecodeResult,
    decode_nec,
    encode_nec,
    encode_nec_repeat,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fuzz(pulses: list[int], factor: float) -> list[int]:
    """Scale every duration by *factor* to simulate clock drift."""
    return [int(p * factor) for p in pulses]


# ── encode_nec ────────────────────────────────────────────────────────────────

class TestEncodeNec:
    def test_standard_length(self):
        """Standard NEC frame: 2 header + 32*2 bit + 1 trail = 67 items."""
        seq = encode_nec(0x04, 0x08)
        assert len(seq) == 67

    def test_extended_length(self):
        seq = encode_nec(0x04, 0x08, extended=True)
        assert len(seq) == 67

    def test_auto_extended_on_wide_address(self):
        """Address > 255 should silently switch to extended NEC."""
        seq = encode_nec(0x1234, 0x56)
        assert len(seq) == 67

    def test_header_timings(self):
        seq = encode_nec(0x00, 0x00)
        assert seq[0] == 9_000   # 9 ms header pulse
        assert seq[1] == 4_500   # 4.5 ms header space

    def test_trailing_mark(self):
        seq = encode_nec(0xFF, 0xFF)
        assert seq[-1] == 562

    def test_bad_command_raises(self):
        with pytest.raises(ValueError):
            encode_nec(0x00, 256)

    def test_wide_address_auto_promotes_to_extended(self):
        """address > 255 should silently auto-promote to extended NEC, not raise."""
        seq = encode_nec(0x0100, 0x08)    # 256 decimal
        result = decode_nec(seq)
        assert result is not None
        assert result.protocol == "NECX"
        assert result.address  == 0x0100

    def test_negative_address_raises(self):
        with pytest.raises(ValueError):
            encode_nec(-1, 0x00)

    def test_bad_extended_address_raises(self):
        with pytest.raises(ValueError):
            encode_nec(0x10000, 0x00, extended=True)

    def test_repeat_length(self):
        seq = encode_nec_repeat()
        assert len(seq) == 3
        assert seq[0] == 9_000
        assert seq[1] == 2_250
        assert seq[2] == 562


# ── decode_nec ────────────────────────────────────────────────────────────────

class TestDecodeNec:
    @pytest.mark.parametrize("address,command", [
        (0x00, 0x00),
        (0x04, 0x08),
        (0xFF, 0xFF),
        (0xA5, 0x3C),
    ])
    def test_standard_round_trip(self, address, command):
        seq = encode_nec(address, command)
        result = decode_nec(seq)
        assert result is not None
        assert result.protocol == "NEC"
        assert result.address  == address
        assert result.command  == command
        assert result.repeat   is False

    @pytest.mark.parametrize("address,command", [
        (0x0000, 0x08),
        (0x1234, 0x56),
        (0xFFFF, 0xFF),
        # NOTE: address=0x00FF (255) is excluded here.  On the wire, extended
        # NEC with addr_lo=0xFF addr_hi=0x00 is identical to standard NEC with
        # address=0xFF — the complement check passes for both.  The decoder
        # correctly returns protocol="NEC" for that case.
        (0x0100, 0x00),
        (0x0200, 0xAB),
    ])
    def test_extended_round_trip(self, address, command):
        seq = encode_nec(address, command, extended=True)
        result = decode_nec(seq)
        assert result is not None
        assert result.protocol == "NECX"
        assert result.address  == address
        assert result.command  == command

    def test_scancode_standard(self):
        result = decode_nec(encode_nec(0x04, 0x08))
        assert result.scancode == (0x04 << 8) | 0x08

    def test_scancode_extended(self):
        result = decode_nec(encode_nec(0x1234, 0x56, extended=True))
        assert result.scancode == (0x1234 << 8) | 0x56

    def test_repeat_code(self):
        result = decode_nec(encode_nec_repeat())
        assert result is not None
        assert result.repeat is True

    def test_timing_tolerance_fast(self):
        """Simulate a remote that runs 15 % fast — should still decode."""
        seq = _fuzz(encode_nec(0x10, 0x20), 0.85)
        result = decode_nec(seq)
        assert result is not None
        assert result.address == 0x10
        assert result.command == 0x20

    def test_timing_tolerance_slow(self):
        """Simulate a remote that runs 15 % slow."""
        seq = _fuzz(encode_nec(0x10, 0x20), 1.15)
        result = decode_nec(seq)
        assert result is not None
        assert result.address == 0x10
        assert result.command == 0x20

    def test_too_short_returns_none(self):
        assert decode_nec([]) is None
        assert decode_nec([9_000]) is None
        assert decode_nec([9_000, 4_500]) is None

    def test_bad_header_pulse_returns_none(self):
        seq = encode_nec(0x01, 0x01)
        seq[0] = 1_000  # wrong header pulse
        assert decode_nec(seq) is None

    def test_bad_header_space_returns_none(self):
        seq = encode_nec(0x01, 0x01)
        seq[1] = 1_000  # wrong header space
        assert decode_nec(seq) is None

    def test_corrupt_command_complement_returns_none(self):
        """Flip a bit in the command complement — should fail integrity check."""
        seq = list(encode_nec(0x04, 0x08))
        # The command complement occupies bits 24-31 (indices 50-65 in pulse list).
        # Flip the space of the first command-complement bit (index 51):
        seq[51] = 562 if seq[51] > 562 else 1_688
        assert decode_nec(seq) is None

    def test_repr(self):
        r = DecodeResult("NEC", 0x04, 0x08, 0x0408)
        s = repr(r)
        assert "NEC"    in s
        assert "0x0004" in s   # address rendered as 0x%04X
        assert "0x08"   in s   # command rendered as 0x%02X
