"""
LV-MaxSonar-EZ ultrasonic sensor — ASCII serial protocol parser.

Protocol: ASCII frames at 9600 baud, CR-terminated.
  Format: R<NNN>\r  where NNN is distance in inches (0–254)
  Example: R023\r  = 23 inches
"""

from __future__ import annotations


def parse_line(raw: bytes) -> int | None:
    """
    Parse one ASCII frame.

    Returns distance in inches on success, None on malformed input.
    """
    line = raw.decode("ascii", errors="ignore").strip()
    if len(line) != 4 or line[0] != "R" or not line[1:].isdigit():
        return None
    return int(line[1:])
