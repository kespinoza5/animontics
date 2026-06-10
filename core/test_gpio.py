"""Unit tests for the portable GPIO output-line factory — no hardware required."""
from core.gpio import make_output_line, NullOutputLine


def test_no_spec_is_null():
    line = make_output_line(None)
    assert isinstance(line, NullOutputLine)
    line.set(True)        # must not raise
    line.close()


def test_empty_spec_is_null():
    assert isinstance(make_output_line({}), NullOutputLine)


def test_backend_none_is_null():
    assert isinstance(make_output_line({"backend": "none"}), NullOutputLine)
    assert isinstance(make_output_line({"backend": "null"}), NullOutputLine)


def test_mcu_backend_stub_is_null():
    # Documented seam, not yet implemented → degrades to no-op, not a crash.
    assert isinstance(make_output_line({"backend": "mcu", "device": "x"}), NullOutputLine)


def test_unknown_backend_is_null():
    assert isinstance(make_output_line({"backend": "bogus"}), NullOutputLine)


def test_libgpiod_missing_keys_is_null():
    # libgpiod spec without chip/line must not raise — falls back to null.
    assert isinstance(make_output_line({"backend": "libgpiod"}), NullOutputLine)


def test_libgpiod_unavailable_is_null():
    # On a dev machine without gpiod / the chip, a well-formed spec still degrades
    # gracefully to a NullOutputLine rather than raising.
    line = make_output_line({"backend": "libgpiod", "chip": "gpiochip99", "line": 1})
    assert isinstance(line, NullOutputLine)
    line.set(False)       # must not raise
