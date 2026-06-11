"""mcu_link.py — versioned MCU↔node link frame codec ("wire" v1).

This is the SINGLE source of truth for how an MCU serializes a vector of raw
channel samples onto its uplink. It lives in core/ because the node decodes with
it at runtime (core/ is deployed to boards; tools/ is not); forge re-exports it
as tools.forge.protocol and the firmware's transport module encodes the identical
layout (mcu/<family>/modules/transport_serial). Keep the three in lockstep — the
constants below are authoritative.

Frame layout v1 (little-endian, self-delimiting for a raw serial stream):

    Offset  Size   Field
    0       2      magic    = b'AM'        (sync marker)
    2       1      version  = 1
    3       1      seq      uint8          (wraps 0..255; lets the node spot drops)
    4       1      count    uint8          (number of int16 channels that follow)
    5       2*N    samples  int16[N] LE    (signed raw counts)
    5+2N    1      checksum uint8          (sum of all preceding bytes & 0xFF)

    Total = 6 + 2*N + 1 bytes.

Samples are signed int16 raw counts (fits AVR 10-bit 0..1023 and ADS1115
single-ended 0..32767; signed covers differential ADS1115). Calibration and
unit conversion are NOT here — the node owns all meaning. A wider/float payload
is a future v2 (bump VERSION), decoded by branching on the version byte.
"""
from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass

MAGIC = b"AM"
VERSION = 1
MAX_CHANNELS = 255

_HEADER = struct.Struct("<2sBBB")   # magic, version, seq, count
_MIN_FRAME = _HEADER.size + 1       # header + checksum, with zero channels

# ── Command frames (node → MCU) ───────────────────────────────────────────────
# A separate, opposite-direction frame so the MCU can take simple actuator
# commands. Distinct magic ('AC') so neither end mistakes one for an uplink
# sample frame. Layout mirrors the uplink frame; args are int16 (e.g. set_duty
# takes [channel, duty]).
CMD_MAGIC = b"AC"
CMD_VERSION = 1
CMD_SET_DUTY = 1                     # args: [channel, duty(0..255)]
CMD_SET_US = 2                       # args: [channel, microseconds] — servo pulse width
CMD_SET_GPIO = 3                     # args: [channel, 0|1] — digital output line

_CMD_HEADER = struct.Struct("<2sBBB")   # magic, version, cmd_id, nargs


@dataclass(frozen=True)
class Frame:
    """A decoded uplink frame: a sequence number and the raw int16 samples."""

    seq: int
    samples: tuple[int, ...]
    version: int = VERSION


def frame_size(count: int) -> int:
    """Total on-wire bytes for a frame carrying `count` int16 channels."""
    return _HEADER.size + 2 * count + 1


def encode(samples: Sequence[int], seq: int = 0) -> bytes:
    """Serialize one frame of int16 samples. Raises ValueError on >255 channels."""
    count = len(samples)
    if count > MAX_CHANNELS:
        raise ValueError(f"too many channels: {count} (max {MAX_CHANNELS})")
    body = _HEADER.pack(MAGIC, VERSION, seq & 0xFF, count)
    body += struct.pack(f"<{count}h", *samples)
    return body + bytes([sum(body) & 0xFF])


def decode(frame: bytes) -> Frame | None:
    """Decode one complete frame.

    Returns None if the bytes are not exactly one well-formed frame (bad magic,
    unknown version, wrong length, or checksum mismatch).
    """
    if len(frame) < _MIN_FRAME:
        return None
    magic, version, seq, count = _HEADER.unpack_from(frame, 0)
    if magic != MAGIC or version != VERSION:
        return None
    if len(frame) != frame_size(count):
        return None
    if (sum(frame[:-1]) & 0xFF) != frame[-1]:
        return None
    samples = struct.unpack_from(f"<{count}h", frame, _HEADER.size)
    return Frame(seq=seq, samples=samples)


class FrameStream:
    """Stateful, resyncing decoder for a raw serial byte stream.

    Feed it whatever bytes arrive; it returns complete, checksum-valid frames and
    keeps partial data buffered, resyncing on the magic marker after garbage or a
    corrupt frame. This is what the node-side read loop uses (the MCU emits a
    continuous stream with no external framing).
    """

    def __init__(self, max_buffer: int = 4096) -> None:
        self._buf = bytearray()
        self._max = max_buffer

    def feed(self, data: bytes) -> list[Frame]:
        """Append bytes and return every complete frame now available."""
        self._buf.extend(data)
        out: list[Frame] = []
        while self._extract(out):
            pass
        # Bound the buffer if we never sync (e.g. wrong baud → endless garbage).
        if len(self._buf) > self._max:
            del self._buf[: len(self._buf) - self._max]
        return out

    def _extract(self, out: list[Frame]) -> bool:
        """Try to pull one frame from the buffer. Returns True if it made progress."""
        buf = self._buf
        i = buf.find(MAGIC)
        if i < 0:
            # No magic yet — drop all but a possible trailing first-magic-byte.
            keep = 1 if buf and buf[-1] == MAGIC[0] else 0
            del buf[: len(buf) - keep]
            return False
        if i > 0:
            del buf[:i]                       # discard garbage before the marker
        if len(buf) < _HEADER.size:
            return False                      # need the rest of the header
        _, _, _, count = _HEADER.unpack_from(buf, 0)
        total = frame_size(count)
        if len(buf) < total:
            return False                      # wait for the full frame
        frame = decode(bytes(buf[:total]))
        if frame is None:
            del buf[:1]                       # corrupt — step past this magic, resync
            return True
        del buf[:total]
        out.append(frame)
        return True


# ── Command codec (node → MCU) ────────────────────────────────────────────────

@dataclass(frozen=True)
class Command:
    """A decoded command frame: an opcode and its int16 arguments."""

    cmd_id: int
    args: tuple[int, ...]
    version: int = CMD_VERSION


def encode_command(cmd_id: int, args: Sequence[int] = ()) -> bytes:
    """Serialize a command frame (e.g. encode_command(CMD_SET_DUTY, [ch, duty]))."""
    n = len(args)
    if n > MAX_CHANNELS:
        raise ValueError(f"too many args: {n} (max {MAX_CHANNELS})")
    body = _CMD_HEADER.pack(CMD_MAGIC, CMD_VERSION, cmd_id & 0xFF, n)
    body += struct.pack(f"<{n}h", *args)
    return body + bytes([sum(body) & 0xFF])


def decode_command(frame: bytes) -> Command | None:
    """Decode one complete command frame, or None if malformed."""
    if len(frame) < _CMD_HEADER.size + 1:
        return None
    magic, version, cmd_id, n = _CMD_HEADER.unpack_from(frame, 0)
    if magic != CMD_MAGIC or version != CMD_VERSION:
        return None
    if len(frame) != _CMD_HEADER.size + 2 * n + 1:
        return None
    if (sum(frame[:-1]) & 0xFF) != frame[-1]:
        return None
    return Command(cmd_id, struct.unpack_from(f"<{n}h", frame, _CMD_HEADER.size))
