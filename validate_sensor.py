import serial
import sys

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyAMA0"
BAUD = 115200


def parse_frame(frame: bytes):
    if frame[0] != 0x59 or frame[1] != 0x59:
        return None
    if (sum(frame[:8]) & 0xFF) != frame[8]:
        return None
    dist_cm = frame[2] | (frame[3] << 8)
    strength = frame[4] | (frame[5] << 8)
    return dist_cm, strength


print(f"Opening {PORT} at {BAUD} baud — Ctrl+C to quit\n")

try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
except Exception as e:
    sys.exit(f"ERROR: {e}")

print("Port opened OK. Waiting for frames...\n")

while True:
    try:
        b = ser.read(1)
        if not b or b[0] != 0x59:
            continue
        b2 = ser.read(1)
        if not b2 or b2[0] != 0x59:
            continue
        rest = ser.read(7)
        if len(rest) < 7:
            continue
        result = parse_frame(bytes([0x59, 0x59]) + rest)
        if result is None:
            print("bad checksum — skipping")
            continue
        dist_cm, strength = result
        dist_m = dist_cm / 100
        print(f"  {dist_m:.3f} m  ({dist_cm} cm)   strength: {strength}")
    except KeyboardInterrupt:
        print("\nDone.")
        break
    except Exception as e:
        print(f"Read error: {e}")
