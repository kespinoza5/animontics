import json
import logging
import queue
import signal
import sys
import threading
import time

import serial
from flask import Flask, Response, render_template


def _sensor_line() -> str:
    d = _latest.get("distance_cm")
    if d is None:
        return ""
    s = _latest.get("strength", 0)
    t = _latest.get("temp_c", 0.0)
    return f"  {d / 100:.3f} m ({d} cm)  |  strength: {s}  |  temp: {t:.1f} °C    "


class _SensorAwareHandler(logging.StreamHandler):
    def emit(self, record):
        msg = self.format(record)
        sys.stdout.write(f"\r\033[K{msg}\n{_sensor_line()}")
        sys.stdout.flush()


_wz = logging.getLogger("werkzeug")
_wz.handlers.clear()
_wz.addHandler(_SensorAwareHandler())


def _sigint_handler(sig, frame):
    print()
    sys.exit(0)


signal.signal(signal.SIGINT, _sigint_handler)

app = Flask(__name__)

SERIAL_PORT = "/dev/ttyAMA0"
BAUD_RATE = 115200
MAX_QUEUE = 10

_clients: list[queue.Queue] = []
_clients_lock = threading.Lock()
_latest: dict = {"distance_cm": None, "strength": None}


def _parse_frame(frame: bytes) -> tuple[int, int, float] | None:
    if frame[0] != 0x59 or frame[1] != 0x59:
        return None
    if (sum(frame[:8]) & 0xFF) != frame[8]:
        return None
    dist_cm = frame[2] | (frame[3] << 8)
    strength = frame[4] | (frame[5] << 8)
    temp_c = ((frame[7] << 8) | frame[6]) / 8.0 - 256.0
    return dist_cm, strength, temp_c


def _broadcast(payload: str) -> None:
    with _clients_lock:
        for q in _clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass


def serial_reader() -> None:
    global _latest
    while True:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            print(f"Opened {SERIAL_PORT}")
            while True:
                b = ser.read(1)
                if not b or b[0] != 0x59:
                    continue
                b2 = ser.read(1)
                if not b2 or b2[0] != 0x59:
                    continue
                rest = ser.read(7)
                if len(rest) < 7:
                    continue
                result = _parse_frame(bytes([0x59, 0x59]) + rest)
                if result is None:
                    continue
                dist_cm, strength, temp_c = result
                _latest = {"distance_cm": dist_cm, "strength": strength, "temp_c": temp_c}
                payload = json.dumps(
                    {"distance_cm": dist_cm, "strength": strength, "temp_c": temp_c, "ts": time.time()}
                )
                _broadcast(payload)
                sys.stdout.write(f"\r{_sensor_line()}")
                sys.stdout.flush()
        except serial.SerialException as e:
            print(f"Serial error: {e} — retrying in 2s")
            time.sleep(2)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/stream")
def stream():
    q: queue.Queue = queue.Queue(maxsize=MAX_QUEUE)
    with _clients_lock:
        _clients.append(q)

    def generate():
        try:
            if _latest["distance_cm"] is not None:
                payload = json.dumps({**_latest, "ts": time.time()})
                yield f"data: {payload}\n\n"
            while True:
                try:
                    data = q.get(timeout=25)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _clients_lock:
                if q in _clients:
                    _clients.remove(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


if __name__ == "__main__":
    threading.Thread(target=serial_reader, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True)
