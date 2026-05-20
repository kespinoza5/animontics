#!/usr/bin/env python3
"""
VL53L1X time-of-flight sensor server. Serves SSE on port 5000.

Usage:
  python3 vl53l1x_server.py                  # Adafruit driver (default)
  python3 vl53l1x_server.py --driver smbus2  # custom smbus2 driver

Dependencies:
  pip3 install smbus2 flask
  pip3 install adafruit-circuitpython-vl53l1x   # for --driver ada
"""

import argparse
import collections
import json
import logging
import queue
import signal
import sys
import threading
import time

from flask import Flask, Response, jsonify

# ── CLI args ───────────────────────────────────────────────────────────────────

_parser = argparse.ArgumentParser(description="VL53L1X sensor server")
_parser.add_argument(
    "--driver", choices=["ada", "smbus2"], default="ada",
    help="Sensor driver: ada (Adafruit, default) or smbus2 (custom)",
)
_parser.add_argument(
    "-v", "--verbose", action="count", default=0,
    help="-v debug logs  -vv adds register-level I2C traces",
)
_args = _parser.parse_args()

# ── Config ─────────────────────────────────────────────────────────────────────

I2C_BUS   = 3
VL53_ADDR = 0x29
HOST      = "0.0.0.0"
PORT      = 5000
MAX_QUEUE = 10
DEBUG     = _args.verbose >= 2   # register-level I2C traces

logging.basicConfig(
    level=logging.DEBUG if _args.verbose >= 1 else logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── Mode state ─────────────────────────────────────────────────────────────────

_target_mode = 2          # 1 = short, 2 = medium, 3 = long
_mode_event  = threading.Event()

# Adafruit distance_mode: 1=short, 2=medium, 3=long  (maps 1:1 to our mode numbers)
# smbus2 register values match the Adafruit library source for each mode.
# The default config blob already sets mode 3 (long), so mode 3 needs no register writes.
# Adafruit library only supports distance_mode 1 (short) and 2 (long).
# Medium uses distance_mode=2 with a shorter timing budget (less integration = shorter range).
_MODES = {
    1: {"label": "short",  "max_mm": 1300, "ada_dm": 1, "ada_tb": 50},
    2: {"label": "medium", "max_mm": 2000, "ada_dm": 2, "ada_tb": 50},   # practical ~2 m with 50 ms budget
    3: {"label": "long",   "max_mm": 4000, "ada_dm": 2, "ada_tb": 100},
}

# ── Auto-ranging ────────────────────────────────────────────────────────────────

_auto_mode       = False
_auto_buf        = collections.deque(maxlen=4)   # rolling window of recent mm values
_auto_consec_oor = 0                             # consecutive OOR/null readings

# (switch-up threshold mm, switch-down threshold mm)  —  None = no switch that direction.
# Thresholds are accuracy-driven, not just range-driven:
#   short mode has measurably lower noise below 1 m; long mode (100 ms) improves SNR above 1.7 m.
#   Hysteresis bands: short↔medium 700–1050 mm, medium↔long 1300–1700 mm.
_AUTO_THRESH = {
    1: (1050, None),    # short  → medium at 1050 mm
    2: (1700, 500),     # medium → long at 1700 mm; → short at 500 mm  (550 mm hysteresis band)
    3: (None, 1100),    # long   → medium at 1100 mm                   (600 mm hysteresis band)
}

def _auto_check(mm, current_mode):
    """Evaluate auto-range logic. Returns new mode (may be same)."""
    global _auto_consec_oor
    if mm is None:
        _auto_consec_oor += 1
        _auto_buf.append(None)
    else:
        _auto_consec_oor = 0
        _auto_buf.append(mm)

    # Immediate up-switch on 2 consecutive OOR readings
    if _auto_consec_oor >= 2 and current_mode < 3:
        _auto_buf.clear()
        _auto_consec_oor = 0
        return current_mode + 1

    if len(_auto_buf) < _auto_buf.maxlen:
        return current_mode   # window not full yet

    valid = [v for v in _auto_buf if v is not None]
    if not valid:
        return current_mode   # handled by OOR path above

    avg = sum(valid) / len(valid)
    up_thresh, down_thresh = _AUTO_THRESH[current_mode]

    if up_thresh and avg > up_thresh and current_mode < 3:
        _auto_buf.clear()
        return current_mode + 1
    if down_thresh and avg < down_thresh and current_mode > 1:
        _auto_buf.clear()
        return current_mode - 1
    return current_mode

# ── Driver import ──────────────────────────────────────────────────────────────

_USE_ADAFRUIT = (_args.driver == "ada")

if _USE_ADAFRUIT:
    try:
        import board
        import busio
        import adafruit_vl53l1x as _adafruit_mod
        log.info("Driver: Adafruit circuitpython-vl53l1x")
    except ImportError:
        log.error("Adafruit driver not installed — run: pip3 install adafruit-circuitpython-vl53l1x")
        sys.exit(1)
else:
    import smbus2
    log.info("Driver: custom smbus2")

# ── Custom smbus2 VL53L1X driver ───────────────────────────────────────────────

if not _USE_ADAFRUIT:

    _FIRMWARE__SYSTEM_STATUS                          = 0x00E5
    _IDENTIFICATION__MODEL_ID                         = 0x010F
    _VHV_CONFIG__TIMEOUT_MACROP_LOOP_BOUND            = 0x0008
    _SYSTEM__MODE_START                               = 0x002B
    _SYSTEM__INTERRUPT_CLEAR                          = 0x0086
    _GPIO__TIO_HV_STATUS                              = 0x0031
    _RESULT__RANGE_STATUS                             = 0x0089
    _RESULT__FINAL_CROSSTALK_CORRECTED_RANGE_MM_SD0   = 0x0096

    # ST ULD default config blob, registers 0x002D–0x0087
    _DEFAULT_CONFIG = [
        0x00, 0x00, 0x00, 0x01, 0x02, 0x00, 0x02, 0x08,
        0x00, 0x08, 0x10, 0x01, 0x01, 0x00, 0x00, 0x00,
        0x00, 0xFF, 0x00, 0x0F, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x20, 0x0B, 0x00, 0x00, 0x02, 0x0A, 0x21,
        0x00, 0x00, 0x05, 0x00, 0x00, 0x00, 0x00, 0xC8,
        0x00, 0x00, 0x38, 0xFF, 0x01, 0x00, 0x08, 0x00,
        0x00, 0x01, 0xCC, 0x0F, 0x01, 0xF1, 0x0D, 0x01,
        0x68, 0x00, 0x80, 0x08, 0xB8, 0x00, 0x00, 0x00,
        0x00, 0x0F, 0x89, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x01, 0x0F, 0x0D, 0x0E, 0x0E, 0x00,
        0x00, 0x02, 0xC7, 0xFF, 0x9B, 0x00, 0x00, 0x00,
        0x01, 0x00, 0x00,
    ]

    class VL53L1X:
        def __init__(self, bus, addr=0x29):
            self._bus  = bus
            self._addr = addr

        def _rd(self, reg):
            wr = smbus2.i2c_msg.write(self._addr, [(reg >> 8) & 0xFF, reg & 0xFF])
            rd = smbus2.i2c_msg.read(self._addr, 1)
            self._bus.i2c_rdwr(wr, rd)
            val = list(rd)[0]
            if DEBUG:
                log.debug("  RD  0x%04X -> 0x%02X", reg, val)
            return val

        def _rd16(self, reg):
            wr = smbus2.i2c_msg.write(self._addr, [(reg >> 8) & 0xFF, reg & 0xFF])
            rd = smbus2.i2c_msg.read(self._addr, 2)
            self._bus.i2c_rdwr(wr, rd)
            data = list(rd)
            return (data[0] << 8) | data[1]

        def _wr(self, reg, val):
            if DEBUG:
                log.debug("  WR  0x%04X <- 0x%02X", reg, int(val) & 0xFF)
            self._bus.i2c_rdwr(
                smbus2.i2c_msg.write(self._addr, [(reg >> 8) & 0xFF, reg & 0xFF, int(val) & 0xFF])
            )

        def _wr16(self, reg, val):
            self._bus.i2c_rdwr(
                smbus2.i2c_msg.write(self._addr, [
                    (reg >> 8) & 0xFF, reg & 0xFF,
                    (val >> 8) & 0xFF, val & 0xFF,
                ])
            )

        def _wr_block(self, start_reg, data):
            for i, val in enumerate(data):
                self._wr(start_reg + i, val)

        def init(self):
            model_id = self._rd(_IDENTIFICATION__MODEL_ID)
            log.info("VL53L1X model ID: 0x%02X (expect 0xEA)", model_id)
            if model_id != 0xEA:
                raise RuntimeError("Unexpected model ID 0x{:02X}".format(model_id))

            log.info("Waiting for firmware boot…")
            deadline = time.time() + 2.0
            while self._rd(_FIRMWARE__SYSTEM_STATUS) != 0x03:
                if time.time() > deadline:
                    raise RuntimeError("Firmware boot timeout")
                time.sleep(0.01)

            self._wr_block(0x002D, _DEFAULT_CONFIG)
            self._wr(_VHV_CONFIG__TIMEOUT_MACROP_LOOP_BOUND, 0x09)
            self._wr(0x000B, 0x00)
            log.info("VL53L1X init done")

        def set_distance_mode(self, mode):
            """Set ranging mode. Register values match the Adafruit library source.
            Mode 3 (long) is the default config blob state — skip if already there."""
            if mode == 1:      # short  ~1.3 m
                self._wr(0x004B, 0x14)
                self._wr(0x0060, 0x07)
                self._wr(0x0063, 0x05)
                self._wr(0x0069, 0x38)
                self._wr16(0x0078, 0x0705)
                self._wr16(0x007A, 0x0606)
            elif mode == 2:    # medium ~3 m
                self._wr(0x004B, 0x0A)
                self._wr(0x0060, 0x0B)
                self._wr(0x0063, 0x09)
                self._wr(0x0069, 0x78)
                self._wr16(0x0078, 0x0B09)
                self._wr16(0x007A, 0x0A0A)
            else:              # long   ~4 m  (mode 3 — same as default config blob)
                self._wr(0x004B, 0x0A)
                self._wr(0x0060, 0x0F)
                self._wr(0x0063, 0x0D)
                self._wr(0x0069, 0xB8)
                self._wr16(0x0078, 0x0F0D)
                self._wr16(0x007A, 0x0E0E)

        def start_continuous(self):
            self._wr(_SYSTEM__MODE_START, 0x40)

        def read_mm(self, timeout=1.0):
            deadline = time.time() + timeout
            while not (self._rd(_GPIO__TIO_HV_STATUS) & 0x01):
                if time.time() > deadline:
                    return None
                time.sleep(0.001)

            status   = self._rd(_RESULT__RANGE_STATUS) & 0x1F
            distance = self._rd16(_RESULT__FINAL_CROSSTALK_CORRECTED_RANGE_MM_SD0)
            self._wr(_SYSTEM__INTERRUPT_CLEAR, 0x01)

            if status not in (0, 9):
                if DEBUG:
                    log.debug("range status %d — discarding", status)
                return None
            return distance

# ── Flask SSE server ───────────────────────────────────────────────────────────

app = Flask(__name__)

_clients      = []
_clients_lock = threading.Lock()
_latest       = {}


def _broadcast(payload_str, event=None):
    frame = ""
    if event:
        frame += "event: {}\n".format(event)
    frame += "data: {}\n\n".format(payload_str)
    with _clients_lock:
        for q in _clients:
            try:
                q.put_nowait(frame)
            except queue.Full:
                pass


def _readout_line():
    d = _latest.get("distance_mm")
    if d is None:
        return ""
    return "  {:4d} mm  ({:.3f} m)   ".format(d, d / 1000.0)


class _SensorAwareHandler(logging.StreamHandler):
    def emit(self, record):
        msg = self.format(record)
        sys.stdout.write("\r\033[K{}\n{}\r".format(msg, _readout_line()))
        sys.stdout.flush()


_wz = logging.getLogger("werkzeug")
_wz.handlers.clear()
_wz.propagate = False
_wz.addHandler(_SensorAwareHandler())


def _sigint_handler(sig, frame):
    print()
    sys.exit(0)


signal.signal(signal.SIGINT, _sigint_handler)


@app.route("/")
def index():
    return (
        "<h3>VL53L1X server — driver: {}</h3>"
        "<p>Open <code>vl53l0x_viewer.html</code> in your browser.</p>"
        "<p>SSE stream: <a href='/stream'>/stream</a></p>"
        "<p>Set mode: <a href='/setmode/1'>/setmode/1</a> (short) &nbsp; "
        "<a href='/setmode/2'>/setmode/2</a> (long)</p>"
    ).format("Adafruit" if _USE_ADAFRUIT else "smbus2")


@app.route("/setmode/<int:mode>")
def set_mode(mode):
    global _target_mode, _auto_mode
    if mode not in _MODES:
        return jsonify({"error": "mode must be 1, 2, or 3"}), 400
    _auto_mode = False          # manual selection cancels auto
    _auto_buf.clear()
    _target_mode = mode
    _mode_event.set()
    _broadcast(json.dumps({"auto": False}), event="auto")
    resp = jsonify({"ok": True, "mode": mode, "max_mm": _MODES[mode]["max_mm"], "label": _MODES[mode]["label"]})
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/setauto/<int:state>")
def set_auto(state):
    global _auto_mode
    _auto_mode = bool(state)
    _auto_buf.clear()
    _broadcast(json.dumps({"auto": _auto_mode}), event="auto")
    resp = jsonify({"ok": True, "auto": _auto_mode})
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/stream")
def stream():
    q = queue.Queue(maxsize=MAX_QUEUE)
    with _clients_lock:
        _clients.append(q)

    def generate():
        try:
            if _latest:
                yield "data: {}\n\n".format(json.dumps(dict(_latest, ts=time.time())))
            m = _MODES[_target_mode]
            yield "event: mode\ndata: {}\n\n".format(
                json.dumps({"mode": _target_mode, "max_mm": m["max_mm"], "label": m["label"]})
            )
            yield "event: auto\ndata: {}\n\n".format(json.dumps({"auto": _auto_mode}))
            while True:
                try:
                    yield q.get(timeout=25)
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


# ── Sensor loops ───────────────────────────────────────────────────────────────
# Mode changes: the loop returns cleanly → sensor_thread restarts immediately
# with the new _target_mode. Exceptions → 3 s retry delay.

def _sensor_loop_adafruit():
    global _latest, _target_mode
    _mode_event.clear()          # discard any stale event from before this init
    i2c = busio.I2C(board.SCL, board.SDA)
    sensor = _adafruit_mod.VL53L1X(i2c)
    current_mode = _target_mode
    cfg = _MODES[current_mode]
    sensor.distance_mode = cfg["ada_dm"]   # library only accepts 1 or 2
    sensor.timing_budget = cfg["ada_tb"]
    sensor.start_ranging()
    log.debug("Adafruit VL53L1X ready — mode %d (%s)",
              current_mode, _MODES[current_mode]["label"])

    while True:
        if _mode_event.is_set():
            _mode_event.clear()
            new_mode = _target_mode
            if new_mode != current_mode:
                sensor.stop_ranging()
                log.debug("Mode → %d (%s) — reinitialising", new_mode, _MODES[new_mode]["label"])
                _broadcast(
                    json.dumps({"mode": new_mode,
                                "max_mm": _MODES[new_mode]["max_mm"],
                                "label": _MODES[new_mode]["label"]}),
                    event="mode",
                )
                return  # sensor_thread will restart the loop with new _target_mode

        if sensor.data_ready:
            status_byte = sensor._read_register(0x0089)[0] & 0x1F
            raw = sensor._read_register(0x0096, 2)
            raw_mm = (raw[0] << 8) + raw[1]
            sensor.clear_interrupt()

            mm = raw_mm if status_byte in (0, 9) else None
            if mm is not None:
                _latest = {"distance_mm": mm}
                sys.stdout.write("\r" + _readout_line())
                sys.stdout.flush()
            _broadcast(json.dumps({"distance_mm": mm, "ts": time.time()}))

            if _auto_mode:
                suggested = _auto_check(mm, current_mode)
                if suggested != current_mode:
                    log.debug("Auto: %s → %s", _MODES[current_mode]["label"], _MODES[suggested]["label"])
                    _target_mode = suggested
                    _mode_event.set()

        time.sleep(0.005)


def _sensor_loop_smbus():
    global _latest, _target_mode
    _mode_event.clear()          # discard any stale event from before this init
    bus = smbus2.SMBus(I2C_BUS)
    sensor = VL53L1X(bus, VL53_ADDR)
    sensor.init()                # default config blob sets mode 3 (long)
    current_mode = _target_mode
    if current_mode != 3:
        sensor.set_distance_mode(current_mode)   # mode 3 is already the default
    sensor.start_continuous()
    log.debug("smbus2 VL53L1X ready — mode %d (%s)", current_mode, _MODES[current_mode]["label"])

    while True:
        if _mode_event.is_set():
            _mode_event.clear()
            new_mode = _target_mode
            if new_mode != current_mode:
                log.debug("Mode → %d (%s) — reinitialising", new_mode, _MODES[new_mode]["label"])
                _broadcast(
                    json.dumps({"mode": new_mode,
                                "max_mm": _MODES[new_mode]["max_mm"],
                                "label": _MODES[new_mode]["label"]}),
                    event="mode",
                )
                return  # sensor_thread will restart the loop with new _target_mode

        mm = sensor.read_mm(timeout=0.2)
        if mm is not None:
            _latest = {"distance_mm": mm}
            sys.stdout.write("\r" + _readout_line())
            sys.stdout.flush()
        _broadcast(json.dumps({"distance_mm": mm, "ts": time.time()}))

        if _auto_mode:
            suggested = _auto_check(mm, current_mode)
            if suggested != current_mode:
                log.debug("Auto: %s → %s", _MODES[current_mode]["label"], _MODES[suggested]["label"])
                _target_mode = suggested
                _mode_event.set()


def sensor_thread():
    while True:
        try:
            if _USE_ADAFRUIT:
                _sensor_loop_adafruit()
            else:
                _sensor_loop_smbus()
        except Exception as e:
            log.error("Sensor error: %s — retrying in 3s", e)
            time.sleep(3)


if __name__ == "__main__":
    threading.Thread(target=sensor_thread, daemon=True).start()
    app.run(host=HOST, port=PORT, threaded=True)
