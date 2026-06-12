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
    #: The chip's eight conversion rates (SPS) → DR field bits [7:5].
    DATA_RATES = {8: 0b000, 16: 0b001, 32: 0b010, 64: 0b011,
                  128: 0b100, 250: 0b101, 475: 0b110, 860: 0b111}

    def __init__(self, device_id: str, config: "DeviceConfig") -> None:
        super().__init__(device_id, config)
        self._bus_no = config.bus if config.bus is not None else 1
        self._addr = config.address if config.address is not None else 0x48
        rate = int((config.params or {}).get("data_rate", 128))
        if rate not in self.DATA_RATES:
            raise ValueError(
                f"ads1115 data_rate {rate} not supported (one of {sorted(self.DATA_RATES)})")
        self._rate = rate
        # config: OS=1 | MUX(AIN_n single-ended) | PGA(gain) | MODE single-shot |
        #         DR=data_rate | comparator disabled
        self._base = 0x8000 | 0x0100 | (self.DATA_RATES[rate] << 5) | 0b00011
        # conversion time + 15% margin (e.g. ~9 ms at 128 SPS, ~144 ms at 8 SPS)
        self._wait_s = 1.15 / rate
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
        config = self._base | ((0b100 | channel) << 12) | ((gain & 0b111) << 9)
        with self._lock:
            try:
                self._bus.write_i2c_block_data(
                    self._addr, self._CONFIG, [(config >> 8) & 0xFF, config & 0xFF]
                )
                time.sleep(self._wait_s)       # one conversion at the configured rate
                hi, lo = self._bus.read_i2c_block_data(self._addr, self._CONV, 2)
            except OSError as exc:
                log.warning("device %s: ADS1115 read failed — %s", self.id, exc)
                return None
        raw = (hi << 8) | lo
        return raw - 0x10000 if raw & 0x8000 else raw
