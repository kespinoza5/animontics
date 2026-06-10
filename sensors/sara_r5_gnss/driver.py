"""NMEA sentence parser for the SARA-R5 GNSS stream.

Parses $GxRMC and $GxGGA sentences (and their multi-constellation $GN variants)
into a flat dict of signal values. All hardware I/O lives in SaraR5Device; this
module is pure parsing — no serial, no threading.
"""
from __future__ import annotations

import re
from typing import Any


def _checksum_ok(sentence: str) -> bool:
    """Verify the NMEA XOR checksum after the '*'."""
    if "*" not in sentence:
        return False
    body, cs = sentence[1:].rsplit("*", 1)
    expected = 0
    for ch in body:
        expected ^= ord(ch)
    try:
        return int(cs[:2], 16) == expected
    except ValueError:
        return False


def _lat(raw: str, hemi: str) -> float | None:
    """NMEA lat DDMM.mmm + N/S → decimal degrees."""
    if not raw or not hemi:
        return None
    try:
        deg = int(raw[:2])
        minutes = float(raw[2:])
        val = deg + minutes / 60.0
        return -val if hemi == "S" else val
    except (ValueError, IndexError):
        return None


def _lon(raw: str, hemi: str) -> float | None:
    """NMEA lon DDDMM.mmm + E/W → decimal degrees."""
    if not raw or not hemi:
        return None
    try:
        deg = int(raw[:3])
        minutes = float(raw[3:])
        val = deg + minutes / 60.0
        return -val if hemi == "W" else val
    except (ValueError, IndexError):
        return None


def _float(s: str) -> float | None:
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _int(s: str) -> int | None:
    try:
        return int(s) if s else None
    except ValueError:
        return None


def _parse_rmc(fields: list[str]) -> dict[str, Any]:
    """$GxRMC,time,status,lat,N,lon,E,speed_kn,course,date,..."""
    if len(fields) < 10:
        return {}
    status = fields[2]
    lat = _lat(fields[3], fields[4])
    lon = _lon(fields[5], fields[6])
    speed_kn = _float(fields[7])
    course = _float(fields[8])
    time_str = fields[1]      # hhmmss.ss
    date_str = fields[9]      # ddmmyy

    utc_time: str | None = None
    if len(time_str) >= 6 and len(date_str) == 6:
        try:
            h, m = int(time_str[:2]), int(time_str[2:4])
            s = float(time_str[4:])
            d, mo, y = int(date_str[:2]), int(date_str[2:4]), int(date_str[4:])
            utc_time = f"20{y:02d}-{mo:02d}-{d:02d}T{h:02d}:{m:02d}:{s:05.2f}Z"
        except (ValueError, IndexError):
            pass

    return {
        "rmc_valid": status == "A",
        "latitude": lat,
        "longitude": lon,
        "speed_kph": round(speed_kn * 1.852, 2) if speed_kn is not None else None,
        "heading_deg": course,
        "utc_time": utc_time,
    }


def _parse_gga(fields: list[str]) -> dict[str, Any]:
    """$GxGGA,time,lat,N,lon,E,fix_quality,sats,hdop,alt,M,..."""
    if len(fields) < 10:
        return {}
    lat = _lat(fields[2], fields[3])
    lon = _lon(fields[4], fields[5])
    fix_quality = _int(fields[6])
    satellites = _int(fields[7])
    hdop = _float(fields[8])
    alt_m = _float(fields[9])

    return {
        "latitude": lat,
        "longitude": lon,
        "fix_quality": fix_quality,
        "satellites": satellites,
        "hdop": hdop,
        "alt_m": alt_m,
    }


# Sentence type → parser; only the talker-id prefix varies ($GP, $GN, $GL, $GA)
_PARSERS = {
    "RMC": _parse_rmc,
    "GGA": _parse_gga,
}
_SENTENCE_RE = re.compile(r"^\$[A-Z]{2}([A-Z]{3}),(.*)$")


def parse_nmea_sentence(line: str) -> dict[str, Any] | None:
    """Parse one NMEA sentence into a partial reading dict, or None to discard."""
    if not line.startswith("$"):
        return None
    # Strip and verify checksum
    clean = line.split("*")[0] if "*" in line else line
    if not _checksum_ok(line) and "*" in line:
        return None
    m = _SENTENCE_RE.match(clean)
    if not m:
        return None
    sentence_type = m.group(1)
    parser = _PARSERS.get(sentence_type)
    if parser is None:
        return None
    fields = (clean[1:]).split(",")   # includes talker+type as field[0]
    try:
        return parser(fields)
    except Exception:
        return None
