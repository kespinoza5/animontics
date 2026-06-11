#!/usr/bin/env python3
"""
MLX90640 ASCII heatmap viewer — reads 768 float temps from serial (COM16)
and renders a live 32x24 colored heatmap in the terminal.

Expected serial format: 768 comma- or space-separated floats per line.
Baud rate default: 115200. Change BAUD if your firmware uses another rate.
"""

import sys
import serial
import time

PORT = "COM16"
#BAUD = 9600
#BAUD = 38400
#BAUD = 57600
BAUD = 115200
#BAUD = 230400

COLS = 32
ROWS = 24

# ASCII gradient from cold to hot (16 chars)
CHARS = " .:-=+*#%@█"

# ANSI 256-color background palette — blue→cyan→green→yellow→red
COLOR_STOPS = [
    (21,),   # blue
    (27,),   # blue-cyan
    (51,),   # cyan
    (46,),   # green
    (226,),  # yellow
    (208,),  # orange
    (196,),  # red
]

def ansi_bg(code: int) -> str:
    return f"\x1b[48;5;{code}m"

def ansi_fg(code: int) -> str:
    return f"\x1b[38;5;{code}m"

RESET = "\x1b[0m"
CLEAR = "\x1b[H"           # move cursor to top-left without clearing (smoother)
CLEAR_SCREEN = "\x1b[2J\x1b[H"

def lerp_color(t: float) -> int:
    """Map t in [0,1] to a 256-color terminal palette index."""
    t = max(0.0, min(1.0, t))
    n = len(COLOR_STOPS) - 1
    lo = int(t * n)
    hi = min(lo + 1, n)
    return COLOR_STOPS[lo][0] if lo == hi else COLOR_STOPS[lo][0]

def temp_to_char(t: float, tmin: float, tmax: float) -> tuple[str, int]:
    span = tmax - tmin or 1.0
    frac = (t - tmin) / span
    char = CHARS[int(frac * (len(CHARS) - 1))]
    color = lerp_color(frac)
    return char, color

def render_frame(frame: list[float]) -> None:
    tmin = min(frame)
    tmax = max(frame)
    rows_out = []
    for r in range(ROWS):
        row_chars = []
        for c in range(COLS):
            idx = r * COLS + c
            ch, color = temp_to_char(frame[idx], tmin, tmax)
            row_chars.append(f"{ansi_bg(color)}{ansi_fg(255)}{ch}{ch}{RESET}")
        rows_out.append("".join(row_chars))

    header = (
        f"  MLX90640  32×24  |  "
        f"min: {tmin:6.2f}°C  "
        f"max: {tmax:6.2f}°C  "
        f"span: {tmax-tmin:.2f}°C"
    )
    sys.stdout.write(CLEAR)
    sys.stdout.write(header + "\n")
    sys.stdout.write("  " + "─" * 65 + "\n")
    for row in rows_out:
        sys.stdout.write("  " + row + "\n")
    sys.stdout.write("  " + "─" * 65 + "\n")
    sys.stdout.write("  [Ctrl+C to quit]\n")
    sys.stdout.flush()

def parse_frame(line: str) -> list[float] | None:
    """Parse a line of 768 floats (comma or space separated)."""
    try:
        parts = line.replace(",", " ").split()
        if len(parts) != COLS * ROWS:
            return None
        return [float(p) for p in parts]
    except ValueError:
        return None

def main() -> None:
    print(f"Opening {PORT} at {BAUD} baud...")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=2)
    except serial.SerialException as e:
        print(f"Error: {e}")
        sys.exit(1)

    print("Waiting for first frame...")
    sys.stdout.write(CLEAR_SCREEN)
    sys.stdout.flush()

    frame_count = 0
    t0 = time.monotonic()

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            frame = parse_frame(line)
            if frame is None:
                continue
            render_frame(frame)
            frame_count += 1
            elapsed = time.monotonic() - t0
            fps = frame_count / elapsed if elapsed > 0 else 0
            # FPS shown in header on next render — stored for debug if needed
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        sys.stdout.write(RESET + "\n")
        print("Closed.")

if __name__ == "__main__":
    main()
