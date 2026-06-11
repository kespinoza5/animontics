import serial
import sys
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyAMA0"
BAUD = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

print(f"Listening on {PORT} @ {BAUD} baud — Ctrl+C to quit\n")

try:
    ser = serial.Serial(PORT, BAUD, timeout=2)
except Exception as e:
    sys.exit(f"ERROR opening port: {e}")

print("Port opened. Reading raw bytes...\n")

while True:
    try:
        chunk = ser.read(32)
        if chunk:
            hex_str = " ".join(f"{b:02X}" for b in chunk)
            print(f"  [{len(chunk):2d} bytes]  {hex_str}")
        else:
            print(f"  (timeout — no bytes received)")
    except KeyboardInterrupt:
        print("\nDone.")
        break
