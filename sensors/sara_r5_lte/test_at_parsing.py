"""Unit tests for AT response parsers — no hardware required."""
from sensors.sara_r5_lte.driver import _parse_cesq, _parse_cereg, _parse_cops


def test_cesq_lte():
    lines = ["+CESQ: 99,99,255,255,26,50"]
    data = _parse_cesq(lines)
    assert data["rsrq_db"] == 26 * 0.5 - 19.5    # -6.5 dB
    assert data["rsrp_dbm"] == 50 - 141           # -91 dBm
    assert data["rssi_dbm"] is None               # rxlev=99 → not known


def test_cesq_unknown():
    lines = ["+CESQ: 99,99,255,255,255,255"]
    data = _parse_cesq(lines)
    assert data["rsrp_dbm"] is None
    assert data["rsrq_db"] is None


def test_cereg_registered():
    lines = ['+CEREG: 2,1,"00A1","0000A1B2",9']
    data = _parse_cereg(lines)
    assert data["registration_state"] == "registered_home"
    assert data["rat"] == "LTE_M1"


def test_cereg_searching():
    lines = ["+CEREG: 2,2"]
    data = _parse_cereg(lines)
    assert data["registration_state"] == "searching"


def test_cops_operator():
    lines = ['+COPS: 0,0,"AT&T",9']
    data = _parse_cops(lines)
    assert data["operator"] == "AT&T"
    assert data["band"] == "LTE_M1"


def test_cops_no_operator():
    lines = ["+COPS: 2"]
    data = _parse_cops(lines)
    assert data["operator"] is None
