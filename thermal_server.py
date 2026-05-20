#!/usr/bin/env python3
"""
MLX90640 thermal camera server — smbus2 only, no blinka/GPIO needed.
Reads 32x24 frames from i2c-3, serves JSON on port 5000.

Dependencies: pip3 install smbus2
Usage:        python3 thermal_server.py
"""

import json
import time
import struct
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread, Lock

import smbus2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

HOST      = "0.0.0.0"
PORT      = 5000
I2C_BUS   = 3
MLX_ADDR  = 0x33

# ── Low-level I2C helpers ─────────────────────────────────────────────────────

def _reg_bytes(reg):
    return [(reg >> 8) & 0xFF, reg & 0xFF]

def read_words(bus, addr, reg, count):
    """Read `count` 16-bit big-endian words via repeated-start."""
    words = []
    chunk = 32          # safe chunk size for most i2c controllers
    for offset in range(0, count, chunk):
        n   = min(chunk, count - offset)
        wr  = smbus2.i2c_msg.write(addr, _reg_bytes(reg + offset))
        rd  = smbus2.i2c_msg.read(addr, n * 2)
        bus.i2c_rdwr(wr, rd)
        raw = bytes(rd)
        for i in range(n):
            w = (raw[i*2] << 8) | raw[i*2+1]
            words.append(w)
    return words

def write_word(bus, addr, reg, value):
    data = _reg_bytes(reg) + [(value >> 8) & 0xFF, value & 0xFF]
    bus.i2c_rdwr(smbus2.i2c_msg.write(addr, data))

# ── MLX90640 driver ───────────────────────────────────────────────────────────

class MLX90640:
    """
    Minimal but complete MLX90640 driver.
    Implements datasheet §11 calibration compensation.
    """

    REFRESH_8HZ = 0b100      # bits [9:7] of control reg 1

    REG_STATUS = 0x8000
    REG_CTRL1  = 0x800D
    REG_EEPROM = 0x2400
    REG_RAM    = 0x0400

    def __init__(self, bus, addr=0x33):
        self.bus  = bus
        self.addr = addr
        log.info("Reading EEPROM…")
        self._ee  = read_words(bus, addr, self.REG_EEPROM, 832)
        log.info("EEPROM ok — extracting calibration…")
        self._p   = {}
        self._extract_params()
        self._set_refresh_rate(self.REFRESH_8HZ)
        log.info("MLX90640 ready")

    # ── refresh rate ─────────────────────────────────────────────────────────

    def _set_refresh_rate(self, rate):
        ctrl = read_words(self.bus, self.addr, self.REG_CTRL1, 1)[0]
        ctrl = (ctrl & 0xFC7F) | ((rate & 0x07) << 7)
        write_word(self.bus, self.addr, self.REG_CTRL1, ctrl)

    # ── calibration (datasheet §11.1) ────────────────────────────────────────

    def _s16(self, v):
        return v - 65536 if v > 32767 else v

    def _s8(self, v):
        return v - 256 if v > 127 else v

    def _extract_params(self):
        ee = self._ee
        p  = self._p
        s16, s8 = self._s16, self._s8

        # VDD
        p['kVdd']  = s8((ee[51] & 0xFF00) >> 8) * 32
        p['vdd25'] = ((( ee[51] & 0x00FF) - 256) << 5) - 8192

        # PTAT
        p['KvPTAT']    = s8((ee[50] & 0xFC00) >> 10, ) if False else \
                         (lambda v: v-64 if v>31 else v)((ee[50]&0xFC00)>>10) / 4096.0
        p['KtPTAT']    = s16(ee[50] & 0x03FF) / 8.0
        if p['KtPTAT'] > 63.875: p['KtPTAT'] = (ee[50]&0x03FF) - 1024 / 8.0
        p['v25']       = 0x6400
        p['alphaPTAT'] = (ee[16] & 0xF000) / 4.0 + 8.0

        # Gain
        p['gainEE'] = s16(ee[48])

        # Tgc
        p['tgc'] = s8(ee[60] & 0x00FF) / 32.0

        # Resolution
        p['resEE'] = (ee[56] & 0x3000) >> 12

        # KsTa
        p['KsTa'] = s8((ee[60] & 0xFF00) >> 8) / 8192.0

        # KsTo
        step = ((ee[63] & 0x3000) >> 12) * 10
        ct2  = (ee[63] & 0x00F0) >> 4
        ct3  = ct2 + ((ee[63] & 0x0F00) >> 8) * step
        p['ct'] = [-40, 0, ct2, ct3]
        ksScale = (ee[63] & 0x000F) + 8
        p['ksTo'] = [0.0]*5
        for i in range(4):
            raw = (ee[61 + i//2] >> (8*(i%2))) & 0xFF
            p['ksTo'][i] = s8(raw) / (1 << ksScale)
        p['ksTo'][4] = -0.0002

        # Per-pixel alpha
        aRemSc  = ee[32] & 0x000F
        aColSc  = (ee[32] & 0x00F0) >> 4
        aRowSc  = (ee[32] & 0x0F00) >> 8
        aSc     = ((ee[32] & 0xF000) >> 12) + 30
        aRef    = ee[33]

        accRow = self._nibble_array(ee, 34, 6, signed7=True)
        accCol = self._nibble_array(ee, 40, 8, signed7=True)

        p['alpha'] = [0.0]*768
        for i in range(768):
            r, c  = divmod(i, 32)
            pix   = ee[64+i]
            aPixEE = (pix & 0x03F0) >> 4
            if aPixEE > 31: aPixEE -= 64
            p['alpha'][i] = (aRef + (accRow[r]<<aRowSc) + (accCol[c]<<aColSc) +
                             (aPixEE<<aRemSc)) / (1<<aSc)

        # Per-pixel offset
        oRemSc  = ee[16] & 0x000F
        oColSc  = (ee[16] & 0x00F0) >> 4
        oRowSc  = (ee[16] & 0x0F00) >> 8
        oRef    = s16(ee[17])

        occRow = self._nibble_array(ee, 18, 6, signed7=True)
        occCol = self._nibble_array(ee, 24, 8, signed7=True)

        p['offset'] = [0]*768
        for i in range(768):
            r, c   = divmod(i, 32)
            pix    = ee[64+i]
            oPixEE = (pix & 0xFC00) >> 10
            if oPixEE > 31: oPixEE -= 64
            p['offset'][i] = (oRef + (occRow[r]<<oRowSc) + (occCol[c]<<oColSc) +
                              (oPixEE<<oRemSc))

        # Kta
        ktaSc1 = ((ee[56] & 0x00F0) >> 4) + 8
        ktaSc2 = ee[56] & 0x000F
        ktaRC  = [
            s8((ee[54]&0xFF00)>>8) / (1<<ktaSc1),  # RoCo
            s8( ee[54]&0x00FF)     / (1<<ktaSc1),  # ReCo
            s8((ee[55]&0xFF00)>>8) / (1<<ktaSc1),  # RoCe
            s8( ee[55]&0x00FF)     / (1<<ktaSc1),  # ReCe
        ]
        p['kta'] = [0.0]*768
        for i in range(768):
            r, c   = divmod(i, 32)
            ktaEE  = (ee[64+i] & 0x000E) >> 1
            if ktaEE > 3: ktaEE -= 8
            idx = (r%2)*2 + (c%2)   # 0=RoCo,1=RoCe,2=ReCo,3=ReCe — remap:
            idx = [0,2,1,3][idx]
            p['kta'][i] = (ktaRC[idx] * (1<<ktaSc1) + (ktaEE<<ktaSc2)) / (1<<ktaSc1)

        # Kv
        kvSc = (ee[56] & 0x0F00) >> 8
        kvRC = [
            (lambda v: v-16 if v>7 else v)((ee[52]&0xF000)>>12) / (1<<kvSc),  # RoCo
            (lambda v: v-16 if v>7 else v)((ee[52]&0x0F00)>>8)  / (1<<kvSc),  # ReCo
            (lambda v: v-16 if v>7 else v)((ee[52]&0x00F0)>>4)  / (1<<kvSc),  # RoCe
            (lambda v: v-16 if v>7 else v)( ee[52]&0x000F)       / (1<<kvSc),  # ReCe
        ]
        p['kv'] = [0.0]*768
        for i in range(768):
            r, c = divmod(i, 32)
            idx  = [0,2,1,3][(r%2)*2+(c%2)]
            p['kv'][i] = kvRC[idx]

        # CP
        aSc_cp   = ((ee[32]&0xF000)>>12) + 27
        cpOff0   = ee[58] & 0x03FF
        if cpOff0 > 511: cpOff0 -= 1024
        cpOff1d  = (ee[58] & 0xFC00) >> 10
        if cpOff1d > 31: cpOff1d -= 64
        p['cpOffset']  = [cpOff0, cpOff0 + cpOff1d]
        p['cpAlpha']   = [(ee[57]&0x03FF) / (1<<aSc_cp), 0.0]
        cpA1d = (ee[57]&0xFC00)>>10
        if cpA1d > 31: cpA1d -= 64
        p['cpAlpha'][1] = p['cpAlpha'][0] * (1 + cpA1d/128.0)
        p['cpKta'] = s8(ee[59]&0x00FF) / (1<<ktaSc1)
        p['cpKv']  = s8((ee[59]&0xFF00)>>8) / (1<<kvSc)

        # Chess vs IL
        p['chess'] = bool((ee[10]&0x0800)>>11)

    def _nibble_array(self, ee, start, nwords, signed7=False):
        """Extract 4-nibble-per-word array (24 or 32 entries)."""
        out = []
        for i in range(nwords):
            w = ee[start+i]
            for shift in [0, 4, 8, 12]:
                v = (w >> shift) & 0xF
                if signed7 and v > 7: v -= 16
                out.append(v)
        return out

    # ── frame acquisition ─────────────────────────────────────────────────────

    def _wait_ready(self, subpage, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = read_words(self.bus, self.addr, self.REG_STATUS, 1)[0]
            if (st & 0x0008) and ((st & 0x0001) == subpage):
                write_word(self.bus, self.addr, self.REG_STATUS, st & ~0x0008)
                return True
            time.sleep(0.005)
        return False

    def get_frame(self, out):
        """Fill out[768] with temperatures in °C (updates both subpages)."""
        for sp in range(2):
            if not self._wait_ready(sp):
                log.warning(f"Timeout waiting for subpage {sp}")
                continue
            ram = read_words(self.bus, self.addr, self.REG_RAM, 832)
            self._compensate(ram, sp, out)

    def _compensate(self, ram, sp, result):
        p   = self._p
        s16 = self._s16

        # VDD
        vddRam = s16(ram[0x06F0 - 0x0400 + 32])  # word 0x072X area; use index
        # Spec: RAM[0x0700] = VDD pixel; use a safe fallback
        try:
            vddRam = s16(ram[0x0700 - 0x0400])
        except IndexError:
            vddRam = 0
        vdd = (vddRam - p['vdd25']) / p['kVdd'] + 3.3 if p['kVdd'] != 0 else 3.3

        # Ta from PTAT
        try:
            ptat    = s16(ram[0x0700 - 0x0400 + 1])
            ptatArt = s16(ram[0x06C0 - 0x0400])
        except IndexError:
            ptat = ptatArt = 0
        if ptatArt != 0:
            ta = (ptatArt / (ptatArt * p['alphaPTAT'] / 134217728.0 + 1) - p['v25']) \
                 / p['KtPTAT'] + 25.0
        else:
            ta = 25.0

        # Gain
        try:
            gainRam = s16(ram[0x070A - 0x0400])
        except IndexError:
            gainRam = p['gainEE']
        gain = p['gainEE'] / gainRam if gainRam != 0 else 1.0

        # CP pixels
        try:
            cp = [s16(ram[0x0708-0x0400]) * gain, s16(ram[0x0709-0x0400]) * gain]
        except IndexError:
            cp = [0.0, 0.0]
        for i in range(2):
            cp[i] -= p['cpOffset'][i] * (1 + p['cpKta']*(ta-25)) * (1 + p['cpKv']*(vdd-3.3))

        tgc = p['tgc']
        Ta4 = (ta + 273.15) ** 4

        for i in range(768):
            # Chess pattern: each subpage covers alternating pixels
            row, col = divmod(i, 32)
            pix_sp   = (row + col) % 2   # chess pattern subpage index
            if p['chess'] and pix_sp != sp:
                continue

            try:
                raw = s16(ram[i]) * gain
            except IndexError:
                continue

            pix_off = p['offset'][i] * (1 + p['kta'][i]*(ta-25)) * (1 + p['kv'][i]*(vdd-3.3))
            raw    -= pix_off

            cpSP   = cp[sp]
            vir    = raw - tgc * cpSP

            alpha  = p['alpha'][i] * (1 + p['KsTa']*(ta-25))
            alpha -= tgc * (p['cpAlpha'][0] + p['cpAlpha'][1]) / 2.0

            if alpha == 0:
                result[i] = ta
                continue

            # Object temp
            to = ((vir / alpha + Ta4) ** 0.25) - 273.15
            result[i] = to


# ── Shared frame buffer ───────────────────────────────────────────────────────

frame_lock  = Lock()
latest      = {"pixels": [20.0]*768, "min": 20.0, "max": 20.0, "ts": 0.0}


def capture_loop(sensor):
    buf = [20.0] * 768
    while True:
        try:
            sensor.get_frame(buf)
            mn, mx = min(buf), max(buf)
            with frame_lock:
                latest["pixels"] = [round(v, 2) for v in buf]
                latest["min"]    = round(mn, 2)
                latest["max"]    = round(mx, 2)
                latest["ts"]     = time.time()
        except Exception as e:
            log.error(f"Frame error: {e}")
            time.sleep(0.5)


# ── HTTP server ───────────────────────────────────────────────────────────────

CORS = {"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, ct, body):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        for k, v in CORS.items(): self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self): self._send(204, "text/plain", b"")

    def do_GET(self):
        if self.path.startswith("/frame"):
            with frame_lock:
                data = dict(latest)
            self._send(200, "application/json", json.dumps(data).encode())
        elif self.path in ("/", "/health"):
            self._send(200, "application/json", b'{"status":"ok"}')
        else:
            self._send(404, "text/plain", b"not found")


if __name__ == "__main__":
    bus    = smbus2.SMBus(I2C_BUS)
    sensor = MLX90640(bus, MLX_ADDR)

    Thread(target=capture_loop, args=(sensor,), daemon=True).start()
    log.info(f"Serving on http://0.0.0.0:{PORT}  —  open thermal_viewer.html on your desktop")
    HTTPServer((HOST, PORT), Handler).serve_forever()
