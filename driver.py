"""
VL53L1X time-of-flight distance sensor — custom smbus2 I2C driver.

Implements the ST ULD protocol directly so no Blinka/GPIO dependency is needed.
Supports three distance modes:
  1 = short  (~1.3 m)
  2 = medium (~2.0 m, 50 ms timing budget)
  3 = long   (~4.0 m, 100 ms timing budget)  ← default after init
"""

from __future__ import annotations

import logging
import time

import smbus2

log = logging.getLogger(__name__)

# ── Register map ──────────────────────────────────────────────────────────────

_FIRMWARE__SYSTEM_STATUS                        = 0x00E5
_IDENTIFICATION__MODEL_ID                       = 0x010F
_VHV_CONFIG__TIMEOUT_MACROP_LOOP_BOUND          = 0x0008
_SYSTEM__MODE_START                             = 0x002B
_SYSTEM__INTERRUPT_CLEAR                        = 0x0086
_GPIO__TIO_HV_STATUS                            = 0x0031
_RESULT__RANGE_STATUS                           = 0x0089
_RESULT__FINAL_CROSSTALK_CORRECTED_RANGE_MM_SD0 = 0x0096

# ST ULD default config blob, loaded to registers 0x002D–0x0087 on init
_DEFAULT_CONFIG = [
    0x00, 0x00, 0x00, 0x01, 0x02, 0x00, 0x02, 0x08,
    0x00, 0x08, 0x10, 0x01, 0x01, 0x00, 0x00, 0x00,
    0x00, 0xFF, 0x00, 0x0F, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x20, 0x0B, 0x00, 0x00, 0x02, 0x0A, 0x21,
    0x00, 0x00, 0x05, 0x00, 0x00, 0x00, 0x00, 0xC8,
    0x00, 0x00, 0x38, 0xFF, 0x01, 0x00, 0x08, 0x00,
    0x00, 0x01, 0xCC, 0x0F, 0x01, 0xF1, 0x0D, 0x01,
    0x68, 0x00, 0x80, 0x08, 0xB8, 0x00, 0x00, 0x00,
    0x00, 0x0F, 0x89, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x01, 0x0F, 0x0D, 0x0E, 0x0E, 0x00,
    0x00, 0x02, 0xC7, 0xFF, 0x9B, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x00,
]

# Mode register values — match Adafruit library source
_MODE_REGS: dict[int, dict] = {
    1: {"label": "short",  "max_mm": 1300,
        0x004B: 0x14, 0x0060: 0x07, 0x0063: 0x05, 0x0069: 0x38,
        0x0078_16: 0x0705, 0x007A_16: 0x0606},
    2: {"label": "medium", "max_mm": 2000,
        0x004B: 0x0A, 0x0060: 0x0B, 0x0063: 0x09, 0x0069: 0x78,
        0x0078_16: 0x0B09, 0x007A_16: 0x0A0A},
    3: {"label": "long",   "max_mm": 4000,
        0x004B: 0x0A, 0x0060: 0x0F, 0x0063: 0x0D, 0x0069: 0xB8,
        0x0078_16: 0x0F0D, 0x007A_16: 0x0E0E},
}


class VL53L1X:
    """
    Low-level smbus2 driver for the ST VL53L1X ToF sensor.

    Usage:
        bus    = smbus2.SMBus(3)
        sensor = VL53L1X(bus, addr=0x29)
        sensor.init()
        sensor.set_distance_mode(3)   # long range
        sensor.start_continuous()
        while True:
            mm = sensor.read_mm()     # returns int or None
    """

    def __init__(self, bus: smbus2.SMBus, addr: int = 0x29) -> None:
        self._bus  = bus
        self._addr = addr

    # ── Register I/O ─────────────────────────────────────────────────────────

    def _rd(self, reg: int) -> int:
        wr = smbus2.i2c_msg.write(self._addr, [(reg >> 8) & 0xFF, reg & 0xFF])
        rd = smbus2.i2c_msg.read(self._addr, 1)
        self._bus.i2c_rdwr(wr, rd)
        return list(rd)[0]

    def _rd16(self, reg: int) -> int:
        wr = smbus2.i2c_msg.write(self._addr, [(reg >> 8) & 0xFF, reg & 0xFF])
        rd = smbus2.i2c_msg.read(self._addr, 2)
        self._bus.i2c_rdwr(wr, rd)
        data = list(rd)
        return (data[0] << 8) | data[1]

    def _wr(self, reg: int, val: int) -> None:
        self._bus.i2c_rdwr(
            smbus2.i2c_msg.write(self._addr, [(reg >> 8) & 0xFF, reg & 0xFF, int(val) & 0xFF])
        )

    def _wr16(self, reg: int, val: int) -> None:
        self._bus.i2c_rdwr(
            smbus2.i2c_msg.write(self._addr, [
                (reg >> 8) & 0xFF, reg & 0xFF,
                (val >> 8) & 0xFF, val & 0xFF,
            ])
        )

    def _wr_block(self, start_reg: int, data: list[int]) -> None:
        for i, val in enumerate(data):
            self._wr(start_reg + i, val)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self) -> None:
        """Load default config blob and wait for firmware boot."""
        model_id = self._rd(_IDENTIFICATION__MODEL_ID)
        log.info("VL53L1X model ID: 0x%02X (expect 0xEA)", model_id)
        if model_id != 0xEA:
            raise RuntimeError(f"Unexpected model ID 0x{model_id:02X}")

        log.info("Waiting for firmware boot…")
        deadline = time.time() + 2.0
        while self._rd(_FIRMWARE__SYSTEM_STATUS) != 0x03:
            if time.time() > deadline:
                raise RuntimeError("Firmware boot timeout")
            time.sleep(0.01)

        self._wr_block(0x002D, _DEFAULT_CONFIG)
        self._wr(_VHV_CONFIG__TIMEOUT_MACROP_LOOP_BOUND, 0x09)
        self._wr(0x000B, 0x00)
        log.info("VL53L1X init complete")

    def set_distance_mode(self, mode: int) -> None:
        """Set ranging mode (1=short, 2=medium, 3=long). Default config is mode 3."""
        cfg = _MODE_REGS[mode]
        self._wr(0x004B, cfg[0x004B])
        self._wr(0x0060, cfg[0x0060])
        self._wr(0x0063, cfg[0x0063])
        self._wr(0x0069, cfg[0x0069])
        self._wr16(0x0078, cfg[0x0078_16])
        self._wr16(0x007A, cfg[0x007A_16])

    def start_continuous(self) -> None:
        self._wr(_SYSTEM__MODE_START, 0x40)

    # ── Reading ───────────────────────────────────────────────────────────────

    def read_mm(self, timeout: float = 1.0) -> int | None:
        """
        Block until a measurement is ready and return distance in mm.
        Returns None on ranging error or timeout.
        """
        deadline = time.time() + timeout
        while not (self._rd(_GPIO__TIO_HV_STATUS) & 0x01):
            if time.time() > deadline:
                return None
            time.sleep(0.001)

        status   = self._rd(_RESULT__RANGE_STATUS) & 0x1F
        distance = self._rd16(_RESULT__FINAL_CROSSTALK_CORRECTED_RANGE_MM_SD0)
        self._wr(_SYSTEM__INTERRUPT_CLEAR, 0x01)

        # Status 0 = valid, 9 = wraparound (still usable)
        return distance if status in (0, 9) else None
