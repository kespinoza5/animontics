import json
import queue
import signal
import sys
import threading
import time
import logging

import serial
from flask import Flask, Response


def _sensor_line() -> str:
    d = _latest.get("distance_cm")
    if d is None:
        return ""
    inch = _latest.get("distance_in", 0)
    return f"  {d / 100:.3f} m ({d} cm)  |  {inch} in    "


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

SERIAL_PORT = "/dev/ttyS0"
BAUD_RATE   = 9600
MAX_QUEUE   = 10

_clients: list[queue.Queue] = []
_clients_lock = threading.Lock()
_latest: dict = {"distance_cm": None, "distance_in": None}


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
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
            print(f"Opened {SERIAL_PORT}")
            while True:
                raw = ser.read_until(b"\r")
                if not raw:
                    continue
                line = raw.decode("ascii", errors="ignore").strip()
                if len(line) != 4 or line[0] != "R" or not line[1:].isdigit():
                    continue
                inches = int(line[1:])
                cm = round(inches * 2.54)
                _latest = {"distance_cm": cm, "distance_in": inches}
                payload = json.dumps({"distance_cm": cm, "distance_in": inches, "ts": time.time()})
                _broadcast(payload)
                sys.stdout.write(f"\r{_sensor_line()}")
                sys.stdout.flush()
        except serial.SerialException as e:
            print(f"Serial error: {e} — retrying in 2s")
            time.sleep(2)


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
