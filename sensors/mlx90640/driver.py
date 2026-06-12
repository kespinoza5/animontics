"""
MLX90640 32×24 IR thermal array — complete smbus2 driver.

Implements full EEPROM calibration extraction and datasheet §11 compensation.
No Adafruit/Blinka dependency required.

Usage:
    import smbus2
    from sensors.mlx90640.driver import MLX90640

    bus    = smbus2.SMBus(3)
    sensor = MLX90640(bus, addr=0x33)   # reads EEPROM on init
    buf    = [20.0] * 768
    while True:
        sensor.get_frame(buf)           # updates buf in-place (°C, row-major 32×24)
        print(min(buf), max(buf))
"""

from __future__ import annotations

import logging
import time

import smbus2

log = logging.getLogger(__name__)


# ── Low-level I2C helpers ─────────────────────────────────────────────────────

def _reg_bytes(reg: int) -> list[int]:
    return [(reg >> 8) & 0xFF, reg & 0xFF]


def read_words(bus: smbus2.SMBus, addr: int, reg: int, count: int) -> list[int]:
    """Read `count` 16-bit big-endian words via repeated-start, chunked for safety."""
    words: list[int] = []
    chunk = 32
    for offset in range(0, count, chunk):
        n  = min(chunk, count - offset)
        wr = smbus2.i2c_msg.write(addr, _reg_bytes(reg + offset))
        rd = smbus2.i2c_msg.read(addr, n * 2)
        bus.i2c_rdwr(wr, rd)
        raw = bytes(rd)
        for i in range(n):
            words.append((raw[i * 2] << 8) | raw[i * 2 + 1])
    return words


def write_word(bus: smbus2.SMBus, addr: int, reg: int, value: int) -> None:
    data = _reg_bytes(reg) + [(value >> 8) & 0xFF, value & 0xFF]
    bus.i2c_rdwr(smbus2.i2c_msg.write(addr, data))


# ── MLX90640 driver ───────────────────────────────────────────────────────────

class MLX90640:
    """
    Complete MLX90640 driver implementing datasheet §11 calibration compensation.

    Reads EEPROM calibration data on construction; subsequent get_frame() calls
    fill a 768-element list with temperatures in °C.
    """

    #: The chip's eight refresh rates (Hz) → bits [9:7] of control register 1.
    REFRESH_CODES = {0.5: 0b000, 1: 0b001, 2: 0b010, 4: 0b011,
                     8: 0b100, 16: 0b101, 32: 0b110, 64: 0b111}

    REG_STATUS = 0x8000
    REG_CTRL1  = 0x800D
    REG_EEPROM = 0x2400
    REG_RAM    = 0x0400

    def __init__(self, bus: smbus2.SMBus, addr: int = 0x33,
                 refresh_hz: float = 8) -> None:
        if refresh_hz not in self.REFRESH_CODES:
            raise ValueError(
                f"mlx90640 refresh_hz {refresh_hz} not supported "
                f"(one of {sorted(self.REFRESH_CODES)})")
        self.refresh_hz = refresh_hz
        self.bus  = bus
        self.addr = addr
        log.info("Reading MLX90640 EEPROM…")
        self._ee = read_words(bus, addr, self.REG_EEPROM, 832)
        log.info("Extracting calibration parameters…")
        self._p: dict = {}
        self._extract_params()
        self._set_refresh_rate(self.REFRESH_CODES[self.refresh_hz])
        log.info("MLX90640 ready (%s Hz, %s mode)", self.refresh_hz,
                 "chess" if self._p["chess"] else "interleaved")

    # ── Refresh rate ──────────────────────────────────────────────────────────

    def _set_refresh_rate(self, rate: int) -> None:
        ctrl = read_words(self.bus, self.addr, self.REG_CTRL1, 1)[0]
        ctrl = (ctrl & 0xFC7F) | ((rate & 0x07) << 7)
        write_word(self.bus, self.addr, self.REG_CTRL1, ctrl)

    # ── Calibration extraction (datasheet §11.1) ──────────────────────────────

    @staticmethod
    def _s16(v: int) -> int:
        return v - 65536 if v > 32767 else v

    @staticmethod
    def _s8(v: int) -> int:
        return v - 256 if v > 127 else v

    def _extract_params(self) -> None:
        ee   = self._ee
        p    = self._p
        s16  = self._s16
        s8   = self._s8

        # VDD
        p["kVdd"]  = s8((ee[51] & 0xFF00) >> 8) * 32
        p["vdd25"] = (((ee[51] & 0x00FF) - 256) << 5) - 8192

        # PTAT
        p["KvPTAT"]    = (lambda v: v - 64 if v > 31 else v)((ee[50] & 0xFC00) >> 10) / 4096.0
        p["KtPTAT"]    = s16(ee[50] & 0x03FF) / 8.0
        if p["KtPTAT"] > 63.875:
            p["KtPTAT"] = (ee[50] & 0x03FF) - 1024 / 8.0
        p["v25"]       = 0x6400
        p["alphaPTAT"] = (ee[16] & 0xF000) / 4.0 + 8.0

        # Gain
        p["gainEE"] = s16(ee[48])

        # Tgc
        p["tgc"] = s8(ee[60] & 0x00FF) / 32.0

        # Resolution
        p["resEE"] = (ee[56] & 0x3000) >> 12

        # KsTa
        p["KsTa"] = s8((ee[60] & 0xFF00) >> 8) / 8192.0

        # KsTo
        step = ((ee[63] & 0x3000) >> 12) * 10
        ct2  = (ee[63] & 0x00F0) >> 4
        ct3  = ct2 + ((ee[63] & 0x0F00) >> 8) * step
        p["ct"] = [-40, 0, ct2, ct3]
        ks_scale = (ee[63] & 0x000F) + 8
        p["ksTo"] = [0.0] * 5
        for i in range(4):
            raw = (ee[61 + i // 2] >> (8 * (i % 2))) & 0xFF
            p["ksTo"][i] = s8(raw) / (1 << ks_scale)
        p["ksTo"][4] = -0.0002

        # Per-pixel alpha
        a_rem_sc = ee[32] & 0x000F
        a_col_sc = (ee[32] & 0x00F0) >> 4
        a_row_sc = (ee[32] & 0x0F00) >> 8
        a_sc     = ((ee[32] & 0xF000) >> 12) + 30
        a_ref    = ee[33]
        acc_row  = self._nibble_array(ee, 34, 6, signed7=True)
        acc_col  = self._nibble_array(ee, 40, 8, signed7=True)

        p["alpha"] = [0.0] * 768
        for i in range(768):
            r, c    = divmod(i, 32)
            pix     = ee[64 + i]
            a_pix   = (pix & 0x03F0) >> 4
            if a_pix > 31:
                a_pix -= 64
            p["alpha"][i] = (a_ref + (acc_row[r] << a_row_sc) + (acc_col[c] << a_col_sc) +
                             (a_pix << a_rem_sc)) / (1 << a_sc)

        # Per-pixel offset
        o_rem_sc = ee[16] & 0x000F
        o_col_sc = (ee[16] & 0x00F0) >> 4
        o_row_sc = (ee[16] & 0x0F00) >> 8
        o_ref    = s16(ee[17])
        occ_row  = self._nibble_array(ee, 18, 6, signed7=True)
        occ_col  = self._nibble_array(ee, 24, 8, signed7=True)

        p["offset"] = [0] * 768
        for i in range(768):
            r, c    = divmod(i, 32)
            pix     = ee[64 + i]
            o_pix   = (pix & 0xFC00) >> 10
            if o_pix > 31:
                o_pix -= 64
            p["offset"][i] = (o_ref + (occ_row[r] << o_row_sc) + (occ_col[c] << o_col_sc) +
                              (o_pix << o_rem_sc))

        # Kta
        kta_sc1 = ((ee[56] & 0x00F0) >> 4) + 8
        kta_sc2 = ee[56] & 0x000F
        kta_rc  = [
            s8((ee[54] & 0xFF00) >> 8) / (1 << kta_sc1),
            s8( ee[54] & 0x00FF)       / (1 << kta_sc1),
            s8((ee[55] & 0xFF00) >> 8) / (1 << kta_sc1),
            s8( ee[55] & 0x00FF)       / (1 << kta_sc1),
        ]
        p["kta"] = [0.0] * 768
        for i in range(768):
            r, c   = divmod(i, 32)
            kta_ee = (ee[64 + i] & 0x000E) >> 1
            if kta_ee > 3:
                kta_ee -= 8
            idx = [0, 2, 1, 3][(r % 2) * 2 + (c % 2)]
            p["kta"][i] = (kta_rc[idx] * (1 << kta_sc1) + (kta_ee << kta_sc2)) / (1 << kta_sc1)

        # Kv
        kv_sc = (ee[56] & 0x0F00) >> 8
        kv_rc = [
            (lambda v: v - 16 if v > 7 else v)((ee[52] & 0xF000) >> 12) / (1 << kv_sc),
            (lambda v: v - 16 if v > 7 else v)((ee[52] & 0x0F00) >> 8)  / (1 << kv_sc),
            (lambda v: v - 16 if v > 7 else v)((ee[52] & 0x00F0) >> 4)  / (1 << kv_sc),
            (lambda v: v - 16 if v > 7 else v)( ee[52] & 0x000F)        / (1 << kv_sc),
        ]
        p["kv"] = [0.0] * 768
        for i in range(768):
            r, c      = divmod(i, 32)
            idx       = [0, 2, 1, 3][(r % 2) * 2 + (c % 2)]
            p["kv"][i] = kv_rc[idx]

        # CP
        a_sc_cp  = ((ee[32] & 0xF000) >> 12) + 27
        cp_off0  = ee[58] & 0x03FF
        if cp_off0 > 511:
            cp_off0 -= 1024
        cp_off1d = (ee[58] & 0xFC00) >> 10
        if cp_off1d > 31:
            cp_off1d -= 64
        p["cpOffset"]  = [cp_off0, cp_off0 + cp_off1d]
        p["cpAlpha"]   = [(ee[57] & 0x03FF) / (1 << a_sc_cp), 0.0]
        cp_a1d = (ee[57] & 0xFC00) >> 10
        if cp_a1d > 31:
            cp_a1d -= 64
        p["cpAlpha"][1] = p["cpAlpha"][0] * (1 + cp_a1d / 128.0)
        p["cpKta"] = s8(ee[59] & 0x00FF) / (1 << kta_sc1)
        p["cpKv"]  = s8((ee[59] & 0xFF00) >> 8) / (1 << kv_sc)

        # Chess vs interleaved pattern
        p["chess"] = bool((ee[10] & 0x0800) >> 11)

    def _nibble_array(self, ee: list[int], start: int, nwords: int, signed7: bool = False) -> list[int]:
        out: list[int] = []
        for i in range(nwords):
            w = ee[start + i]
            for shift in [0, 4, 8, 12]:
                v = (w >> shift) & 0xF
                if signed7 and v > 7:
                    v -= 16
                out.append(v)
        return out

    # ── Frame acquisition ─────────────────────────────────────────────────────

    def _wait_ready(self, subpage: int, timeout: float = 2.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = read_words(self.bus, self.addr, self.REG_STATUS, 1)[0]
            if (st & 0x0008) and ((st & 0x0001) == subpage):
                write_word(self.bus, self.addr, self.REG_STATUS, st & ~0x0008)
                return True
            time.sleep(0.005)
        return False

    def get_frame(self, out: list[float]) -> None:
        """
        Fill out[768] with temperatures in °C (updates both subpages).
        out must be a pre-allocated list of 768 floats.
        """
        for sp in range(2):
            if not self._wait_ready(sp):
                log.warning("Timeout waiting for subpage %d", sp)
                continue
            ram = read_words(self.bus, self.addr, self.REG_RAM, 832)
            self._compensate(ram, sp, out)

    def _compensate(self, ram: list[int], sp: int, result: list[float]) -> None:
        p   = self._p
        s16 = self._s16

        # VDD
        try:
            vdd_ram = s16(ram[0x0700 - 0x0400])
        except IndexError:
            vdd_ram = 0
        vdd = (vdd_ram - p["vdd25"]) / p["kVdd"] + 3.3 if p["kVdd"] != 0 else 3.3

        # Ta from PTAT
        try:
            ptat     = s16(ram[0x0700 - 0x0400 + 1])
            ptat_art = s16(ram[0x06C0 - 0x0400])
        except IndexError:
            ptat = ptat_art = 0
        if ptat_art != 0:
            ta = (ptat_art / (ptat_art * p["alphaPTAT"] / 134217728.0 + 1) - p["v25"]) \
                 / p["KtPTAT"] + 25.0
        else:
            ta = 25.0

        # Gain
        try:
            gain_ram = s16(ram[0x070A - 0x0400])
        except IndexError:
            gain_ram = p["gainEE"]
        gain = p["gainEE"] / gain_ram if gain_ram != 0 else 1.0

        # CP pixels
        try:
            cp = [s16(ram[0x0708 - 0x0400]) * gain, s16(ram[0x0709 - 0x0400]) * gain]
        except IndexError:
            cp = [0.0, 0.0]
        for i in range(2):
            cp[i] -= p["cpOffset"][i] * (1 + p["cpKta"] * (ta - 25)) * (1 + p["cpKv"] * (vdd - 3.3))

        tgc = p["tgc"]
        ta4 = (ta + 273.15) ** 4

        for i in range(768):
            row, col = divmod(i, 32)
            pix_sp   = (row + col) % 2
            if p["chess"] and pix_sp != sp:
                continue

            try:
                raw = s16(ram[i]) * gain
            except IndexError:
                continue

            pix_off = p["offset"][i] * (1 + p["kta"][i] * (ta - 25)) * (1 + p["kv"][i] * (vdd - 3.3))
            raw    -= pix_off

            vir   = raw - tgc * cp[sp]
            alpha = p["alpha"][i] * (1 + p["KsTa"] * (ta - 25))
            alpha -= tgc * (p["cpAlpha"][0] + p["cpAlpha"][1]) / 2.0

            if alpha == 0:
                result[i] = ta
                continue

            result[i] = ((vir / alpha + ta4) ** 0.25) - 273.15
