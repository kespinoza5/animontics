"""Si5351Device — I2C clock generator, programmed once at boot.

The audio clock tree's root: CLK0 carries SCKI to the PCM1808 (which runs in
MASTER mode and derives the shared BCLK/LRCLK from it — see the pizero board
config header). The device produces no data; its whole job is configure-at-
boot + register readback for health. It deliberately does NOT stop the clock
on shutdown: a node restart must never collapse the fleet-wide clock domain.

Frequency plan (AN619): PLL = xtal × (a + b/c) in 600–900 MHz, output =
PLL / divider with an even integer divider. `plan_clock()` is pure and
unit-tested; the register I/O is thin around it.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.device import Device, register_device

if TYPE_CHECKING:
    from core.models import DeviceConfig

log = logging.getLogger(__name__)

_XTAL_HZ = 25_000_000
_PLL_MIN, _PLL_MAX = 600_000_000, 900_000_000
_DENOM = 0xFFFFF                      # max 20-bit fractional denominator

# Register map (AN619)
_REG_STATUS = 0
_REG_OUTPUT_ENABLE = 3
_REG_CLK0_CTRL = 16
_REG_MSNA = 26                        # PLL A feedback MultiSynth
_REG_MS0 = 42                         # CLK0 output MultiSynth
_REG_PLL_RESET = 177


def plan_clock(target_hz: int, xtal_hz: int = _XTAL_HZ) -> tuple[int, int, int, int]:
    """Choose (fb_int, fb_num, fb_denom, out_div) for one output frequency.

    out_div is the smallest even integer divider that puts the PLL in range;
    the feedback fraction then hits the PLL exactly enough for audio use
    (error < 1 Hz at 12.288 MHz). Raises ValueError when out of range.
    """
    if target_hz <= 0:
        raise ValueError("target_hz must be positive")
    out_div = max(4, -(-_PLL_MIN // target_hz))          # ceil, then round up to even
    if out_div % 2:
        out_div += 1
    pll_hz = target_hz * out_div
    if not _PLL_MIN <= pll_hz <= _PLL_MAX:
        raise ValueError(f"no even divider puts {target_hz} Hz in PLL range (got {pll_hz})")
    fb = pll_hz / xtal_hz
    fb_int = int(fb)
    fb_num = round((fb - fb_int) * _DENOM)
    if not 15 <= fb_int <= 90:
        raise ValueError(f"feedback ratio {fb:.3f} outside Si5351 range")
    return fb_int, fb_num, _DENOM, out_div


def _msynth_params(int_part: int, num: int, denom: int) -> list[int]:
    """Encode a MultiSynth (a + b/c) into its 8 register bytes (AN619 §3.2)."""
    p1 = 128 * int_part + (128 * num // denom) - 512
    p2 = 128 * num - denom * (128 * num // denom)
    p3 = denom
    return [
        (p3 >> 8) & 0xFF, p3 & 0xFF,
        (p1 >> 16) & 0x03,
        (p1 >> 8) & 0xFF, p1 & 0xFF,
        ((p3 >> 12) & 0xF0) | ((p2 >> 16) & 0x0F),
        (p2 >> 8) & 0xFF, p2 & 0xFF,
    ]


@register_device("si5351")
class Si5351Device(Device):
    """Si5351A on I2C: program CLK0 at params.clk0_hz, then health-check."""

    def __init__(self, device_id: str, config: "DeviceConfig") -> None:
        super().__init__(device_id, config)
        self._bus_no = config.bus if config.bus is not None else 1
        self._addr = config.address if config.address is not None else 0x60
        self._clk0_hz = int((config.params or {}).get("clk0_hz", 12_288_000))
        self._bus = None
        self._configured = False

    # ── Register I/O ──────────────────────────────────────────────────────────

    def _write(self, reg: int, data: list[int] | int) -> None:
        if isinstance(data, int):
            self._bus.write_byte_data(self._addr, reg, data)
        else:
            self._bus.write_i2c_block_data(self._addr, reg, data)

    def _read(self, reg: int) -> int:
        return self._bus.read_byte_data(self._addr, reg)

    def _program(self) -> None:
        fb_int, fb_num, fb_denom, out_div = plan_clock(self._clk0_hz)
        self._write(_REG_OUTPUT_ENABLE, 0xFF)                  # all outputs off
        self._write(_REG_CLK0_CTRL, 0x80)                      # CLK0 powered down
        self._write(_REG_MSNA, _msynth_params(fb_int, fb_num, fb_denom))
        self._write(_REG_MS0, _msynth_params(out_div, 0, 1))   # integer output divider
        self._write(_REG_PLL_RESET, 0xA0)                      # reset PLL A+B
        # CLK0: powered up, fractional-capable MS0, PLLA, 8 mA drive
        self._write(_REG_CLK0_CTRL, 0x4F)
        self._write(_REG_OUTPUT_ENABLE, 0xFE)                  # enable CLK0 only
        log.info("device %s: CLK0 = %d Hz (fb %d+%d/%d, div %d)",
                 self.id, self._clk0_hz, fb_int, fb_num, fb_denom, out_div)

    # ── Device contract ───────────────────────────────────────────────────────

    def start(self) -> None:
        try:
            import smbus2
            self._bus = smbus2.SMBus(self._bus_no)
            self._program()
            status = self._read(_REG_STATUS)
            self._configured = not (status & 0x80)             # SYS_INIT clear = ready
            if not self._configured:
                log.warning("device %s: Si5351 still initializing (status 0x%02x)",
                            self.id, status)
        except Exception as exc:                               # not Linux / no chip
            log.warning("device %s: Si5351 unavailable — %s", self.id, exc)
            self._bus = None
            self._configured = False

    def stop(self) -> None:
        # Leave the clock RUNNING: the tree feeds other boards (and the FPGA
        # fabric). Only release the bus handle.
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
        self._bus = None

    def is_healthy(self) -> bool:
        return self._configured
