"""
IR protocol codec — pulse/space timing encode and decode.

Pure Python, no hardware dependencies. Used by sensor.py for the mode2
fallback path, and directly testable without any hardware present.

Pulse sequences are list[int] of microsecond durations, starting with a
pulse, alternating pulse / space / pulse / space …  This matches the LIRC
mode2 wire format (without the LIRC_MODE2_* type bits in the upper byte).

Supported protocols
-------------------
  NEC standard  — 8-bit address + 8-bit command (32 bits on wire with
                  complement bytes for error checking).
  NEC extended  — 16-bit address + 8-bit command (32 bits on wire; address
                  is split across two bytes with no complement check).

Timing tolerances
-----------------
  The decoder allows ±40 % on all mark/space durations, which covers
  inexpensive remotes and marginal oscillator accuracy.
"""

from __future__ import annotations

# ── NEC timing constants (microseconds) ──────────────────────────────────────

_NEC_HDR_PULSE  = 9_000    # header mark
_NEC_HDR_SPACE  = 4_500    # header space (data frame)
_NEC_RPT_SPACE  = 2_250    # header space (repeat frame)
_NEC_BIT_PULSE  =   562    # bit mark (same for 0 and 1)
_NEC_BIT_SPACE0 =   562    # logical 0 space
_NEC_BIT_SPACE1 = 1_688    # logical 1 space
_NEC_TRAIL      =   562    # trailing mark (stop bit)

_NEC_BITS       = 32       # bits per frame

_TOL = 0.40                # ±40 % timing tolerance


# ── Internal helpers ──────────────────────────────────────────────────────────

def _near(value: int, target: int, tol: float = _TOL) -> bool:
    """True if *value* is within *tol* of *target*."""
    return abs(value - target) <= target * tol


def _bits_to_pulses(bits: list[int]) -> list[int]:
    """Convert a list of 0/1 bits (LSB-first) to alternating pulse/space durations."""
    seq: list[int] = []
    for bit in bits:
        seq.append(_NEC_BIT_PULSE)
        seq.append(_NEC_BIT_SPACE1 if bit else _NEC_BIT_SPACE0)
    return seq


def _int_to_lsb_bits(value: int, width: int) -> list[int]:
    """Expand *value* into *width* bits, LSB-first."""
    return [(value >> i) & 1 for i in range(width)]


def _lsb_bits_to_int(bits: list[int]) -> int:
    """Collapse LSB-first bit list back to an integer."""
    result = 0
    for i, b in enumerate(bits):
        result |= b << i
    return result


# ── NEC encode ────────────────────────────────────────────────────────────────

def encode_nec(
    address: int,
    command: int,
    *,
    extended: bool = False,
) -> list[int]:
    """
    Encode an NEC IR frame as a pulse/space sequence.

    Parameters
    ----------
    address  : 0-255 for standard NEC; 0-65535 for extended NEC.
    command  : 0-255.
    extended : If True, emit NEC Extended (16-bit address, no address
               complement).  Ignored when *address* > 255 (auto-extended).

    Returns
    -------
    list[int]
        Alternating pulse/space durations in microseconds, starting with the
        9 ms header pulse, ending with the 562 µs trailing mark.
    """
    if not 0 <= command <= 0xFF:
        raise ValueError(f"command must be 0–255, got {command!r}")

    if address > 0xFF:
        extended = True

    if extended:
        if not 0 <= address <= 0xFFFF:
            raise ValueError(f"extended address must be 0–65535, got {address!r}")
        addr_lo = address & 0xFF
        addr_hi = (address >> 8) & 0xFF
        payload = (
            _int_to_lsb_bits(addr_lo,  8) +
            _int_to_lsb_bits(addr_hi,  8) +
            _int_to_lsb_bits(command,  8) +
            _int_to_lsb_bits(~command & 0xFF, 8)
        )
    else:
        if not 0 <= address <= 0xFF:
            raise ValueError(f"address must be 0–255, got {address!r}")
        payload = (
            _int_to_lsb_bits(address,          8) +
            _int_to_lsb_bits(~address & 0xFF,  8) +
            _int_to_lsb_bits(command,           8) +
            _int_to_lsb_bits(~command & 0xFF,   8)
        )

    return (
        [_NEC_HDR_PULSE, _NEC_HDR_SPACE]
        + _bits_to_pulses(payload)
        + [_NEC_TRAIL]
    )


def encode_nec_repeat() -> list[int]:
    """
    Encode a NEC repeat code (sent when a key is held down).

    The repeat frame is: 9 ms pulse + 2.25 ms space + 562 µs pulse.
    """
    return [_NEC_HDR_PULSE, _NEC_RPT_SPACE, _NEC_TRAIL]


# ── NEC decode ────────────────────────────────────────────────────────────────

class DecodeResult:
    """Decoded NEC frame."""

    __slots__ = ("protocol", "address", "command", "scancode", "repeat")

    def __init__(
        self,
        protocol: str,
        address: int,
        command: int,
        scancode: int,
        repeat: bool = False,
    ) -> None:
        self.protocol  = protocol   # "NEC" | "NECX"
        self.address   = address
        self.command   = command
        self.scancode  = scancode   # kernel-style: (address << 8) | command
        self.repeat    = repeat

    def __repr__(self) -> str:
        return (
            f"DecodeResult(protocol={self.protocol!r}, "
            f"address=0x{self.address:04X}, command=0x{self.command:02X}, "
            f"repeat={self.repeat})"
        )


def decode_nec(pulses: list[int]) -> DecodeResult | None:
    """
    Decode a raw pulse/space sequence into an NEC frame.

    Returns a :class:`DecodeResult` on success, ``None`` on any parse failure.

    The decoder handles both standard NEC (8-bit address with complement)
    and Extended NEC (16-bit address without complement).  Repeat codes are
    also recognised and returned with ``repeat=True``.
    """
    if len(pulses) < 3:
        return None

    # ── Header mark ──────────────────────────────────────────────────────────
    if not _near(pulses[0], _NEC_HDR_PULSE):
        return None

    # ── Repeat frame detection ────────────────────────────────────────────────
    if len(pulses) == 3 and _near(pulses[1], _NEC_RPT_SPACE) and _near(pulses[2], _NEC_TRAIL):
        return DecodeResult("NEC", 0, 0, 0, repeat=True)

    # ── Data frame: header space ──────────────────────────────────────────────
    if not _near(pulses[1], _NEC_HDR_SPACE):
        return None

    # ── Bit decoding: expect 32 bit-mark + bit-space pairs + trailing mark ───
    # Total pulses: 2 (header) + 32*2 (bits) + 1 (trail) = 67
    if len(pulses) < 67:
        return None

    bits: list[int] = []
    for i in range(_NEC_BITS):
        mark  = pulses[2 + i * 2]
        space = pulses[3 + i * 2]
        if not _near(mark, _NEC_BIT_PULSE):
            return None
        if _near(space, _NEC_BIT_SPACE0):
            bits.append(0)
        elif _near(space, _NEC_BIT_SPACE1):
            bits.append(1)
        else:
            return None

    # ── Unpack four 8-bit fields (LSB-first) ─────────────────────────────────
    b0 = _lsb_bits_to_int(bits[0:8])   # address / addr_lo
    b1 = _lsb_bits_to_int(bits[8:16])  # ~address / addr_hi
    b2 = _lsb_bits_to_int(bits[16:24]) # command
    b3 = _lsb_bits_to_int(bits[24:32]) # ~command

    # ── Command integrity check (both protocols) ──────────────────────────────
    if (b2 ^ b3) != 0xFF:
        return None  # command complement mismatch — corrupt frame

    command = b2

    # ── Distinguish standard vs extended by address complement ────────────────
    if (b0 ^ b1) == 0xFF:
        # Standard NEC: b1 is the complement of b0
        address  = b0
        protocol = "NEC"
        scancode = (address << 8) | command
    else:
        # Extended NEC: b1 is the high byte of a 16-bit address
        address  = (b1 << 8) | b0
        protocol = "NECX"
        scancode = (address << 8) | command

    return DecodeResult(protocol, address, command, scancode)


# ── Protocol registry (extensible) ───────────────────────────────────────────

#: Maps protocol name → encoder callable.  Add RC5/RC6 here when needed.
ENCODERS: dict[str, object] = {
    "NEC":  encode_nec,
    "NECX": lambda addr, cmd: encode_nec(addr, cmd, extended=True),
}

#: Human-readable names for RC_PROTO_* kernel enum values.
RC_PROTO_NAMES: dict[int, str] = {
    9:  "NEC",
    10: "NECX",
    11: "NEC32",
    2:  "RC5",
    15: "RC6_0",
}
