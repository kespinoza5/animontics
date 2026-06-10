"""AT response parsers for SARA-R5 LTE status.

Parses +CESQ, +CEREG, and +COPS responses into signal-quality dicts.
No I/O here — callers pass `send_at` callables; this module only does text parsing.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


# ── +CESQ (extended signal quality) ──────────────────────────────────────────
# AT+CESQ → +CESQ: <rxlev>,<ber>,<rscp>,<ecno>,<rsrq>,<rsrp>
# LTE fields: rsrq [0..34 → -19.5..-2 dB], rsrp [0..97 → -141..-44 dBm]

def _parse_cesq(lines: list[str]) -> dict[str, Any]:
    for line in lines:
        if not line.startswith("+CESQ:"):
            continue
        try:
            parts = line.split(":", 1)[1].strip().split(",")
            rsrq_raw = int(parts[4].strip())
            rsrp_raw = int(parts[5].strip())
            rsrq = rsrq_raw * 0.5 - 19.5 if 0 <= rsrq_raw <= 34 else None
            rsrp = rsrp_raw - 141 if 0 <= rsrp_raw <= 97 else None
            rxlev_raw = int(parts[0].strip())
            # RXLEV 0..63 → -111..-49 dBm (1 dBm steps); 99 = not known
            rssi = rxlev_raw * 2 - 111 if 0 <= rxlev_raw <= 63 else None
            return {"rsrp_dbm": rsrp, "rsrq_db": rsrq, "rssi_dbm": rssi}
        except (IndexError, ValueError):
            pass
    return {"rsrp_dbm": None, "rsrq_db": None, "rssi_dbm": None}


# ── +CEREG (EPS network registration) ────────────────────────────────────────
# AT+CEREG? → +CEREG: <n>,<stat>[,<tac>,<ci>,<AcT>]

_CEREG_STAT = {
    0: "not_registered",
    1: "registered_home",
    2: "searching",
    3: "denied",
    4: "unknown",
    5: "registered_roaming",
    6: "registered_sms_only_home",
    7: "registered_sms_only_roaming",
}
_CEREG_ACT = {
    0: "GSM", 2: "UTRAN", 3: "GSM_EGPRS", 4: "UTRAN_HSDPA", 5: "UTRAN_HSUPA",
    6: "UTRAN_HSDPA_HSUPA", 7: "LTE", 8: "EC_GSM_IoT", 9: "LTE_M1", 10: "NB_IoT",
}


def _parse_cereg(lines: list[str]) -> dict[str, Any]:
    for line in lines:
        if not line.startswith("+CEREG:"):
            continue
        try:
            raw = line.split(":", 1)[1].strip()
            parts = [p.strip().strip('"') for p in raw.split(",")]
            # n,stat or stat (unsolicited)
            stat_idx = 1 if len(parts) >= 2 else 0
            stat = int(parts[stat_idx])
            act = int(parts[4]) if len(parts) >= 5 else None
            return {
                "registration_state": _CEREG_STAT.get(stat, f"unknown_{stat}"),
                "rat": _CEREG_ACT.get(act) if act is not None else None,
            }
        except (IndexError, ValueError):
            pass
    return {"registration_state": None, "rat": None}


# ── +COPS (operator selection) ────────────────────────────────────────────────
# AT+COPS? → +COPS: <mode>[,<format>,<oper>[,<AcT>]]

def _parse_cops(lines: list[str]) -> dict[str, Any]:
    for line in lines:
        if not line.startswith("+COPS:"):
            continue
        try:
            raw = line.split(":", 1)[1].strip()
            parts = [p.strip().strip('"') for p in raw.split(",")]
            operator = parts[2] if len(parts) >= 3 else None
            act_raw = int(parts[3]) if len(parts) >= 4 else None
            return {
                "operator": operator,
                "band": _CEREG_ACT.get(act_raw) if act_raw is not None else None,
            }
        except (IndexError, ValueError):
            pass
    return {"operator": None, "band": None}


# ── Composite query ───────────────────────────────────────────────────────────

def query_lte_status(send_at: Callable[[str], list[str]]) -> dict[str, Any]:
    """Issue AT commands and return a merged LTE status dict."""
    data: dict[str, Any] = {}
    data.update(_parse_cesq(send_at("AT+CESQ")))
    data.update(_parse_cereg(send_at("AT+CEREG?")))
    data.update(_parse_cops(send_at("AT+COPS?")))
    return data
