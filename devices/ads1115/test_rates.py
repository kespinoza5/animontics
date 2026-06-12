"""Data-rate exposure is pure config — test without hardware."""
import pytest

from core.models import DeviceConfig


def _make(rate=None):
    from devices.ads1115.device import Ads1115Device
    params = {} if rate is None else {"data_rate": rate}
    return Ads1115Device("a", DeviceConfig(id="a", kind="ads1115", params=params))


def test_default_rate_128():
    dev = _make()
    assert dev._rate == 128
    assert abs(dev._wait_s - 1.15 / 128) < 1e-9


def test_all_chip_rates_accepted():
    from devices.ads1115.device import Ads1115Device
    for rate in Ads1115Device.DATA_RATES:
        assert _make(rate)._rate == rate


def test_unsupported_rate_rejected():
    with pytest.raises(ValueError, match="data_rate 100"):
        _make(100)
