import serial
import sys

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyS0"
BAUD = 9600

print(f"Opening {PORT} at {BAUD} baud — Ctrl+C to quit\n")

try:
    ser = serial.Serial(PORT, BAUD, timeout=2)
except Exception as e:
    sys.exit(f"ERROR: {e}")

print("Port opened OK. Waiting for readings...\n")

while True:
    try:
        raw = ser.read_until(b"\r")
        if not raw:
            print("  (timeout)")
            continue
        line = raw.decode("ascii", errors="ignore").strip()
        if len(line) != 4 or line[0] != "R" or not line[1:].isdigit():
            print(f"  bad frame: {repr(raw)}")
            continue
        inches = int(line[1:])
        cm = round(inches * 2.54)
        m = cm / 100
        print(f"  {m:.3f} m ({cm} cm)  |  {inches} in")
    except KeyboardInterrupt:
        print("\nDone.")
        break
    except Exception as e:
        print(f"Read error: {e}")
