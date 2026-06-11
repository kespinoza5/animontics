"""
Correlate ADS1115 analog distance readings with the unknown 7-byte serial frames
to reverse-engineer how distance is encoded in bytes 4-6 of the serial frame.

Usage:
    python test_correlate.py [serial_port]

Default port: /dev/ttyAMA0
Move the sensor to different distances while this runs.
"""

import sys
import time
import threading
import smbus2
import serial

PORT     = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyAMA0"
BAUD     = 9600
I2C_BUS  = 1
ADS_ADDR = 0x48
ADS_CFG  = [0xC3, 0x83]
VCC      = 5.0

FRAME_HEADER = bytes([0x00, 0x2B, 0x00, 0x06])

# ── ADS reader (runs in background thread, always holds latest voltage) ───────

_ads_lock    = threading.Lock()
_ads_voltage = None

def _ads_loop():
    global _ads_voltage
    bus = smbus2.SMBus(I2C_BUS)
    while True:
        try:
            bus.write_i2c_block_data(ADS_ADDR, 0x01, ADS_CFG)
            time.sleep(0.01)
            data = bus.read_i2c_block_data(ADS_ADDR, 0x00, 2)
            raw  = (data[0] << 8) | data[1]
            if raw > 32767:
                raw -= 65536
            v = raw * 4.096 / 32768
            with _ads_lock:
                _ads_voltage = v
        except Exception:
            pass
        time.sleep(0.05)

threading.Thread(target=_ads_loop, daemon=True).start()

def get_ads_inches():
    with _ads_lock:
        v = _ads_voltage
    if v is None:
        return None
    return v * 512 / VCC

# ── Serial frame reader ───────────────────────────────────────────────────────

def iter_frames(ser):
    """Yield 7-byte frames starting with FRAME_HEADER."""
    buf = b''
    while True:
        buf += ser.read(32)
        idx = buf.find(FRAME_HEADER)
        if idx != -1 and len(buf) >= idx + 7:
            yield buf[idx:idx + 7]
            buf = buf[idx + 7:]
        elif len(buf) > 256:
            buf = buf[-64:]

# ── Main ──────────────────────────────────────────────────────────────────────

print(f"Opening {PORT} at {BAUD} baud — Ctrl+C to quit\n")
print(f"{'ADS inches':>12}  {'ADS cm':>8}  │  {'b4':>5} {'b5':>5} {'b6':>5}  │  b4  b5  b6  │  b4_16b  b56_le  b56_be")
print("─" * 95)

try:
    with serial.Serial(PORT, BAUD, timeout=1) as ser:
        for frame in iter_frames(ser):
            ads_in = get_ads_inches()
            if ads_in is None:
                continue

            b4, b5, b6 = frame[4], frame[5], frame[6]
            ads_cm = ads_in * 2.54

            # Candidate decodings of the 3 payload bytes
            b4_as_in   = b4                          # single byte = inches?
            b56_le     = (b6 << 8) | b5              # 16-bit little-endian
            b56_be     = (b5 << 8) | b6              # 16-bit big-endian
            b4_16b     = (b4 << 8) | b5              # b4+b5 big-endian

            print(
                f"{ads_in:12.1f}  {ads_cm:8.1f}  │"
                f"  {b4:5d} {b5:5d} {b6:5d}  │"
                f"  {b4:02X}  {b5:02X}  {b6:02X}  │"
                f"  {b4_16b:6d}   {b56_le:6d}   {b56_be:6d}"
            )

except KeyboardInterrupt:
    print("\nDone.")
except serial.SerialException as e:
    sys.exit(f"Serial error: {e}")
