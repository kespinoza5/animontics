"""Unit tests for the device tier — frame fan-out + command guard (no hardware)."""
from __future__ import annotations

import pytest

from core.device import Ads1115Device, McuSerialDevice, create_device
from core.mcu_link import FrameStream, encode
from core.models import DeviceConfig


def _device() -> McuSerialDevice:
    return McuSerialDevice("d", DeviceConfig(id="d", kind="mcu_serial",
                                             port="/dev/null", baud=115200))


def _frame(samples, seq=0):
    return FrameStream().feed(encode(samples, seq=seq))[0]


def test_dispatch_fans_out_to_all_subscribers():
    dev = _device()
    a, b = [], []
    dev.subscribe(a.append)
    dev.subscribe(b.append)
    dev._dispatch(_frame([1, 2, 3], seq=5))
    assert a[0].seq == b[0].seq == 5
    assert list(a[0].samples) == [1, 2, 3]


def test_one_bad_subscriber_does_not_stop_others():
    dev = _device()
    good = []
    def boom(_frame):
        raise RuntimeError("subscriber blew up")
    dev.subscribe(boom)
    dev.subscribe(good.append)
    dev._dispatch(_frame([0]))            # must not raise
    assert len(good) == 1


def test_send_command_false_when_link_closed():
    # no open serial handle → command refused, not crashed
    assert _device().send_command(1, [0, 128]) is False


def test_create_device_unknown_kind():
    with pytest.raises(ValueError):
        create_device(DeviceConfig(id="x", kind="bogus"))


def test_ads1115_registered_and_safe_without_bus():
    d = create_device(DeviceConfig(id="a", kind="ads1115", bus=1, address=0x48))
    assert isinstance(d, Ads1115Device)
    assert d.is_healthy() is False          # not started → no I2C bus
    assert d.read_channel(0) is None        # graceful without hardware
    assert d.read_channel(9) is None        # out-of-range channel
