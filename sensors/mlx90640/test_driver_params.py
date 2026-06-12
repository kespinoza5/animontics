"""Refresh-rate mapping is pure — test it where the driver can import."""
import pytest

pytest.importorskip("smbus2")   # driver imports it at module level (Linux boards)


def test_refresh_codes_cover_chip_range():
    from sensors.mlx90640.driver import MLX90640
    assert sorted(MLX90640.REFRESH_CODES) == [0.5, 1, 2, 4, 8, 16, 32, 64]
    assert sorted(MLX90640.REFRESH_CODES.values()) == list(range(8))


def test_unsupported_refresh_rejected():
    from sensors.mlx90640.driver import MLX90640
    with pytest.raises(ValueError, match="refresh_hz 3"):
        MLX90640(bus=None, refresh_hz=3)
