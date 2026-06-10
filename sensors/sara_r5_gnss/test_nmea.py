"""Unit tests for the NMEA sentence parser — no hardware required."""
import pytest
from sensors.sara_r5_gnss.driver import parse_nmea_sentence, _checksum_ok


def test_checksum_valid():
    # Classic NMEA example with known-good checksum
    sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
    assert _checksum_ok(sentence)


def test_checksum_invalid():
    sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*FF"
    assert not _checksum_ok(sentence)


def test_parse_gga():
    # $GP prefix; checksum verified: 0x47
    sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
    data = parse_nmea_sentence(sentence)
    assert data is not None
    assert abs(data["latitude"] - 48.1173) < 0.001
    assert abs(data["longitude"] - 11.5167) < 0.001
    assert data["fix_quality"] == 1
    assert data["satellites"] == 8
    assert data["hdop"] == pytest.approx(0.9)
    assert data["alt_m"] == pytest.approx(545.4)


def test_parse_rmc():
    # $GP prefix; checksum verified: 0x68
    sentence = "$GPRMC,225446,A,4916.45,N,12311.12,W,000.5,054.7,191194,020.3,E*68"
    data = parse_nmea_sentence(sentence)
    assert data is not None
    assert data["rmc_valid"] is True
    assert abs(data["latitude"] - 49.2742) < 0.001
    assert abs(data["longitude"] - (-123.1853)) < 0.001
    assert data["speed_kph"] == pytest.approx(0.5 * 1.852, rel=0.01)
    assert data["heading_deg"] == pytest.approx(54.7)


def test_invalid_sentence():
    assert parse_nmea_sentence("not a sentence") is None


def test_unknown_type():
    # $GNGSV (satellites in view) — not parsed, should return None
    sentence = "$GNGSV,3,1,09,02,66,082,45,03,23,229,36,04,52,126,47,07,04,101,*49"
    assert parse_nmea_sentence(sentence) is None
