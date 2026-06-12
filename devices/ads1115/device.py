"""Ads1115Device — an ADS1115 ADC chip on the SBC's I2C bus.

Pull model: a single muxed converter shared by several scalar sensors. Access is
serialized: read_channel() selects the mux+gain, runs one single-shot conversion,
and returns the signed 16-bit count. smbus2 is imported lazily so the package
stays importable without it.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from core.device import Device, register_device

if TYPE_CHECKING:
    from core.models import DeviceConfig

log = logging.getLogger(__name__)


@register_device("ads1115")
class Ads1115Device(Device):
    """An ADS1115 ADC chip on the SBC's I2C bus (pull model)."""

    _CONV, _CONFIG = 0x00, 0x01
    # config: OS=1 | MUX(AIN_n single-ended) | PGA(gain) | MODE single-shot |
    #         DR=128SPS | comparator disabled
    _BASE = 0x8000 | 0x0100 | (0b100 << 5) | 0b00011

    SPEC = {
        "description": "ADS1115 4-channel I2C ADC — pull device, serialized single-shot reads.",
        "optional": ["bus", "address"],
        "params": [],
    }

    def __init__(self, device_id: str, config: "DeviceConfig") -> None:
        super().__init__(device_id, config)
        self._bus_no = config.bus if config.bus is not None else 1
        self._addr = config.address if config.address is not None else 0x48
        self._bus = None
        self._lock = threading.Lock()

    def start(self) -> None:
        try:
            import smbus2
            self._bus = smbus2.SMBus(self._bus_no)
        except Exception as exc:               # not Linux / no bus / no chip
            log.warning("device %s: ADS1115 unavailable — %s", self.id, exc)
            self._bus = None

    def stop(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
        self._bus = None

    def is_healthy(self) -> bool:
        return self._bus is not None

    def read_channel(self, channel: int, gain: int = 1) -> int | None:
        """Single-shot read of single-ended AINx. Returns signed counts, or None."""
        if self._bus is None or not 0 <= channel <= 3:
            return None
        config = self._BASE | ((0b100 | channel) << 12) | ((gain & 0b111) << 9)
        with self._lock:
            try:
                self._bus.write_i2c_block_data(
                    self._addr, self._CONFIG, [(config >> 8) & 0xFF, config & 0xFF]
                )
                time.sleep(0.009)              # ~128 SPS conversion
                hi, lo = self._bus.read_i2c_block_data(self._addr, self._CONV, 2)
            except OSError as exc:
                log.warning("device %s: ADS1115 read failed — %s", self.id, exc)
                return None
        raw = (hi << 8) | lo
        return raw - 0x10000 if raw & 0x8000 else raw
