"""
TF Mini Plus LiDAR — serial frame parser.

Protocol: 9-byte frames at 115200 baud.
  Byte 0–1: 0x59 0x59  (header)
  Byte 2–3: distance (cm, little-endian uint16)
  Byte 4–5: signal strength (little-endian uint16)
  Byte 6–7: chip temperature raw (little-endian uint16)
  Byte 8:   checksum (sum of bytes 0–7, lowest byte)
"""

from __future__ import annotations


def parse_frame(frame: bytes) -> tuple[int, int, float] | None:
    """
    Parse a 9-byte TF Mini Plus frame.

    Returns (distance_cm, strength, temp_c) on success, None on bad frame.
    """
    if len(frame) < 9:
        return None
    if frame[0] != 0x59 or frame[1] != 0x59:
        return None
    if (sum(frame[:8]) & 0xFF) != frame[8]:
        return None

    distance_cm = frame[2] | (frame[3] << 8)
    strength    = frame[4] | (frame[5] << 8)
    temp_raw    = (frame[7] << 8) | frame[6]
    temp_c      = temp_raw / 8.0 - 256.0
    return distance_cm, strength, temp_c
