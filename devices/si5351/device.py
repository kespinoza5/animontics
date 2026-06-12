"""Si5351Device — I2C clock generator, programmed once at boot.

A clock-tree root (e.g. CLK0 carrying SCKI to an audio codec running in
MASTER mode). The Si5351A drives up to THREE outputs (CLK0–CLK2) from two
PLLs, so a config may request at most two distinct frequencies — outputs that
share a frequency share a PLL. The device produces no data; its whole job is
configure-at-boot + register readback for health. It deliberately does NOT
stop the clocks on shutdown: a node restart must never collapse a shared
clock domain.

Frequency plan (AN619): PLL = xtal × (a + b/c) in 600–900 MHz, output =
PLL / divider with an even integer divider. `plan_clock()` (one frequency)
and `plan_outputs()` (PLL assignment across outputs) are pure and
unit-tested; the register I/O is thin around them.
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
_REG_CLK_CTRL = {0: 16, 1: 17, 2: 18}     # CLKi control
_REG_PLL_MSYNTH = {"A": 26, "B": 34}      # PLL feedback MultiSynths
_REG_MS = {0: 42, 1: 50, 2: 58}           # CLKi output MultiSynths
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


def plan_outputs(
    outputs: dict[int, int], xtal_hz: int = _XTAL_HZ,
) -> tuple[dict[str, tuple[int, int, int]], dict[int, tuple[str, int]]]:
    """Assign the two PLLs and per-output dividers for up to three outputs.

    `outputs` maps output index (0–2) → target Hz. Outputs sharing a frequency
    share a PLL; the Si5351A has two PLLs, so at most two DISTINCT frequencies
    are possible. Returns (pll_plans, assignments): pll_plans maps "A"/"B" →
    (fb_int, fb_num, fb_denom); assignments maps output index → (pll, out_div).
    Raises ValueError on a third distinct frequency, a bad output index, or an
    unreachable frequency (via plan_clock).
    """
    if not outputs:
        raise ValueError("no outputs requested")
    bad = sorted(set(outputs) - set(_REG_MS))
    if bad:
        raise ValueError(f"Si5351A has outputs 0-2 (got {bad})")
    freqs = sorted({hz for hz in outputs.values()})
    if len(freqs) > 2:
        raise ValueError(
            f"Si5351A has two PLLs — at most 2 distinct frequencies (asked: {freqs})"
        )
    pll_plans: dict[str, tuple[int, int, int]] = {}
    by_freq: dict[int, tuple[str, int]] = {}
    for pll, hz in zip(("A", "B"), freqs):
        fb_int, fb_num, fb_denom, out_div = plan_clock(hz, xtal_hz)
        pll_plans[pll] = (fb_int, fb_num, fb_denom)
        by_freq[hz] = (pll, out_div)
    return pll_plans, {idx: by_freq[hz] for idx, hz in outputs.items()}


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
    """Si5351A on I2C: program CLK0–CLK2 from params.clk<i>_hz, then health-check."""

    def __init__(self, device_id: str, config: "DeviceConfig") -> None:
        super().__init__(device_id, config)
        self._bus_no = config.bus if config.bus is not None else 1
        self._addr = config.address if config.address is not None else 0x60
        params = config.params or {}
        self._outputs = {
            i: int(params[f"clk{i}_hz"])
            for i in _REG_MS if f"clk{i}_hz" in params
        }
        if not self._outputs:
            self._outputs = {0: 12_288_000}    # historical default: 256 × 48 kHz on CLK0
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
        pll_plans, assignments = plan_outputs(self._outputs)
        self._write(_REG_OUTPUT_ENABLE, 0xFF)                  # all outputs off
        for idx in assignments:
            self._write(_REG_CLK_CTRL[idx], 0x80)              # power down while configuring
        for pll, (fb_int, fb_num, fb_denom) in pll_plans.items():
            self._write(_REG_PLL_MSYNTH[pll], _msynth_params(fb_int, fb_num, fb_denom))
        enable_mask = 0xFF                                     # active-low per output
        for idx, (pll, out_div) in assignments.items():
            self._write(_REG_MS[idx], _msynth_params(out_div, 0, 1))
            # powered up, integer MS, 8 mA drive; bit5 selects PLLB
            self._write(_REG_CLK_CTRL[idx], 0x4F | (0x20 if pll == "B" else 0x00))
            enable_mask &= ~(1 << idx)
            log.info("device %s: CLK%d = %d Hz (PLL%s, div %d)",
                     self.id, idx, self._outputs[idx], pll, out_div)
        self._write(_REG_PLL_RESET, 0xA0)                      # reset PLL A+B
        self._write(_REG_OUTPUT_ENABLE, enable_mask)

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
