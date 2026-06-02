"""
IR transceiver driver — low-level LIRC device I/O.

No threading, no HTTP, no global state. All functions operate on a file
descriptor returned by open_lirc_rx / open_lirc_tx, which the caller is
responsible for closing via close_lirc().

On non-Linux hosts (Windows dev machines) the module imports cleanly; calls
that touch hardware will raise OSError or ImportError at runtime, which is
expected and handled by sensor.py.
"""

from __future__ import annotations

import os
import struct

try:
    import fcntl as _fcntl
    _FCNTL_AVAILABLE = True
except ImportError:
    _fcntl = None           # type: ignore[assignment]
    _FCNTL_AVAILABLE = False

from sensors.ir_xcvr.codec import RC_PROTO_NAMES, encode_nec

# ── LIRC mode constants ───────────────────────────────────────────────────────

LIRC_MODE_SCANCODE = 0x08
LIRC_MODE_PULSE    = 0x02
LIRC_MODE_MODE2    = 0x04

# ── LIRC ioctls — _IOW('i', nr, u32) = 0x40046900 | nr ──────────────────────

LIRC_SET_REC_MODE     = 0x40046919
LIRC_SET_SEND_MODE    = 0x40046911
LIRC_SET_SEND_CARRIER = 0x40046913   # carrier frequency in Hz

# ── lirc_scancode struct ──────────────────────────────────────────────────────
# struct lirc_scancode {
#     __u64 timestamp;   // monotonic nanoseconds
#     __u16 flags;
#     __u16 rc_proto;    // enum rc_proto
#     __u32 keycode;
#     __u64 scancode;
# };

SC_FMT  = "<QHHIQ"
SC_SIZE = struct.calcsize(SC_FMT)    # 24 bytes

SCANCODE_FLAG_REPEAT = 0x02

# ── LIRC mode2 type bits (upper byte of each u32) ────────────────────────────

MODE2_SPACE    = 0x00000000
MODE2_PULSE    = 0x01000000
MODE2_TIMEOUT  = 0x03000000
MODE2_MASK     = 0xFF000000

# RC_PROTO enum values (include/uapi/linux/lirc.h)
RC_PROTO_NEC  = 9
RC_PROTO_NECX = 10

IR_CARRIER_HZ = 38_000


# ── RX ────────────────────────────────────────────────────────────────────────

def open_lirc_rx(device: str) -> tuple[int, bool]:
    """
    Open a LIRC receiver device and configure it for reading.

    Tries LIRC_MODE_SCANCODE first (preferred — kernel decodes protocol).
    Falls back to LIRC_MODE_MODE2 (raw pulse/space) if the ioctl fails.

    Returns
    -------
    (fd, scancode_mode)
        fd            : open file descriptor (caller must close)
        scancode_mode : True → read 24-byte lirc_scancode structs
                        False → read 4-byte mode2 pulse/space words
    """
    if not _FCNTL_AVAILABLE:
        raise OSError("fcntl not available — this platform is not Linux")

    fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)

    mode = struct.pack("<I", LIRC_MODE_SCANCODE)
    try:
        _fcntl.ioctl(fd, LIRC_SET_REC_MODE, mode)
        return fd, True
    except OSError:
        pass

    mode = struct.pack("<I", LIRC_MODE_MODE2)
    _fcntl.ioctl(fd, LIRC_SET_REC_MODE, mode)
    return fd, False


def read_one_scancode(fd: int) -> tuple[str, int, int, int, bool] | None:
    """
    Read one lirc_scancode struct from *fd* (non-blocking).

    Returns
    -------
    (protocol, address, command, scancode, repeat) or None if no data.

    Raises OSError on device error.
    """
    raw = os.read(fd, SC_SIZE)
    if len(raw) < SC_SIZE:
        return None

    _ts, flags, rc_proto, _keycode, scancode = struct.unpack(SC_FMT, raw)

    repeat   = bool(flags & SCANCODE_FLAG_REPEAT)
    protocol = RC_PROTO_NAMES.get(rc_proto, f"PROTO_{rc_proto}")

    if rc_proto == RC_PROTO_NEC:
        address = (scancode >> 8) & 0xFF
        command = scancode & 0xFF
    elif rc_proto == RC_PROTO_NECX:
        address = (scancode >> 8) & 0xFFFF
        command = scancode & 0xFF
    else:
        address = int(scancode >> 8)
        command = int(scancode & 0xFF)

    return protocol, address, command, int(scancode), repeat


def read_one_mode2_word(fd: int) -> tuple[str, int] | None:
    """
    Read one 4-byte mode2 word from *fd* (non-blocking).

    Returns
    -------
    (kind, duration_us) where kind is "pulse" | "space" | "timeout" | "other",
    or None if no data.
    """
    raw = os.read(fd, 4)
    if len(raw) < 4:
        return None

    word     = struct.unpack("<I", raw)[0]
    kind_raw = word & MODE2_MASK
    duration = word & ~MODE2_MASK

    if kind_raw == MODE2_PULSE:
        kind = "pulse"
    elif kind_raw == MODE2_SPACE:
        kind = "space"
    elif kind_raw == MODE2_TIMEOUT:
        kind = "timeout"
    else:
        kind = "other"

    return kind, duration


# ── TX ────────────────────────────────────────────────────────────────────────

def open_lirc_tx(device: str) -> tuple[int, bool]:
    """
    Open a LIRC transmitter device and configure it for sending.

    Tries LIRC_MODE_SCANCODE first (kernel handles carrier modulation).
    Falls back to LIRC_MODE_PULSE + sets 38 kHz carrier.

    Returns
    -------
    (fd, scancode_mode)
    """
    if not _FCNTL_AVAILABLE:
        raise OSError("fcntl not available — this platform is not Linux")

    fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)

    mode = struct.pack("<I", LIRC_MODE_SCANCODE)
    try:
        _fcntl.ioctl(fd, LIRC_SET_SEND_MODE, mode)
        return fd, True
    except OSError:
        pass

    mode = struct.pack("<I", LIRC_MODE_PULSE)
    _fcntl.ioctl(fd, LIRC_SET_SEND_MODE, mode)

    carrier = struct.pack("<I", IR_CARRIER_HZ)
    _fcntl.ioctl(fd, LIRC_SET_SEND_CARRIER, carrier)

    return fd, False


def write_scancode(fd: int, protocol: str, address: int, command: int) -> bool:
    """
    Transmit one IR code via the LIRC scancode interface.

    The kernel's pwm-ir-tx driver handles carrier generation and pulse timing.

    Returns True if the full struct was written.
    """
    proto_map = {"NEC": RC_PROTO_NEC, "NECX": RC_PROTO_NECX}
    rc_proto  = proto_map.get(protocol.upper())
    if rc_proto is None:
        return False

    scancode = (address << 8) | command
    payload  = struct.pack(SC_FMT, 0, 0, rc_proto, 0, scancode)
    written  = os.write(fd, payload)
    return written == SC_SIZE


def write_raw_pulses(fd: int, pulses: list[int]) -> bool:
    """
    Transmit a raw pulse/space sequence via the LIRC pulse interface.

    *pulses* is a list of microsecond durations starting with a pulse,
    as returned by codec.encode_nec().  No type bits — the kernel assumes
    alternating pulse/space.

    Returns True if all bytes were written.
    """
    raw     = struct.pack(f"<{len(pulses)}I", *pulses)
    written = os.write(fd, raw)
    return written == len(raw)


def close_lirc(fd: int) -> None:
    """Close a LIRC file descriptor, ignoring errors."""
    try:
        os.close(fd)
    except OSError:
        pass
