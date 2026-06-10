"""Unit tests for SaraR5Device's AT/NMEA demux — no hardware required."""
from core.models import DeviceConfig
from devices.sara_r5.device import SaraR5Device


def _dev() -> SaraR5Device:
    # Empty params → null GPIO lines; we never open the serial port in these tests.
    return SaraR5Device("sara", DeviceConfig(id="sara", kind="sara_r5"))


def test_nmea_lines_go_to_gnss_subscribers():
    dev = _dev()
    seen = []
    dev.subscribe_gnss(seen.append)
    dev._route("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47")
    dev._route("+UULOC: 1,2,3")
    assert len(seen) == 2
    assert seen[0].startswith("$GPGGA")


def test_at_lines_accumulate_until_ok():
    dev = _dev()
    assert not dev._at_ready.is_set()
    dev._route("+CESQ: 99,99,255,255,26,50")
    assert not dev._at_ready.is_set()      # no terminator yet
    dev._route("OK")
    assert dev._at_ready.is_set()          # terminator releases the waiter
    assert "+CESQ: 99,99,255,255,26,50" in dev._at_buf


def test_error_terminator_releases():
    dev = _dev()
    dev._route("+CME ERROR: 100")
    assert dev._at_ready.is_set()


def test_gnss_line_does_not_touch_at_buffer():
    dev = _dev()
    dev.subscribe_gnss(lambda _l: None)
    dev._route("$GPRMC,225446,A,4916.45,N,12311.12,W,000.5,054.7,191194,020.3,E*68")
    assert dev._at_buf == []
    assert not dev._at_ready.is_set()


def test_null_gpio_lines_are_safe():
    # No power_line/reset_line in params → make_output_line returns NullOutputLine;
    # power_on / reset must be no-op safe (used by the run loop before serial opens).
    dev = _dev()
    dev._stop.set()                        # short-circuit the settle waits
    dev._power_line.set(True)              # must not raise
    dev.reset_modem()                      # must not raise
