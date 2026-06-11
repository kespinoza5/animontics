from __future__ import annotations

import math
import struct

from core.analog_array import AnalogArrayBase
from core.mcu_link import Frame
from core.registry import register
from sensors.pressure_array.driver import to_kpa


@register("pressure_array")
class PressureArray(AnalogArrayBase):
    """A logical pressure surface read across one or more MCU devices.

    Two shapes, decided by config:

    **Flat array** (no `row_tag` channels): every channel is a static tap;
    AnalogArrayBase composes the per-device frames into one reading and
    `enrich` adds kPa for `linear`-calibrated channels. The original
    cranial-pressure shape.

    **Scanned lattice** (`params.rows` + one `row_tag` channel per device):
    the velostat lattice is energized one row at a time by a conductor MCU
    (see mcu/circuit_python/modules/matrix_scan), so each device frame is
    *one row's worth* of that device's columns, tagged with the row index in
    its `row_tag` channel (-1 = the follower saw no conductor). This class
    accumulates rows per device, freezes a device's sweep when its row
    counter wraps, and when every device has a frozen sweep composes the
    full rows x columns grid:

      - JSON lane: latest raw values + a `sweep` summary (n / complete /
        missing cells / follower timeouts) — light, for status + scalars.
      - Binary frame lane (`/sensors/<id>/frames`): the full grid as
        float32, header `<IHHff` = (sweep_n, rows, cols, min, max), row-major,
        NaN for cells a device never delivered. Columns are the non-row_tag
        channels in config order.

    A device that laps the others (double wrap before composition) forces a
    partial emit so a dead follower degrades to `complete: false`, never to
    silence — mirroring the firmware's -1 sentinel philosophy.
    """

    sensor_type = "pressure_array"
    produces_frames = True

    _FRAME_HEADER = struct.Struct("<IHHff")   # sweep_n, rows, cols, min, max

    def __init__(self, sensor_id, config) -> None:
        super().__init__(sensor_id, config)
        self._rows = int((config.params or {}).get("rows", 0))
        self._row_ch: dict[str, int] = {}                  # device → row-tag index
        self._dev_cols: dict[str, list[tuple[int, str]]] = {}   # device → [(index, signal)]
        self._cols: list[tuple[str, str]] = []             # grid columns: (device, signal)
        for ch in config.channels:
            if (ch.calibration or {}).get("type") == "row_tag":
                if ch.device:
                    self._row_ch[ch.device] = ch.index
            elif ch.device:
                self._dev_cols.setdefault(ch.device, []).append((ch.index, ch.signal))
                self._cols.append((ch.device, ch.signal))
        # Sweep accumulation (guarded by the base's lock — ingest is per-device-thread)
        self._acc: dict[str, dict[int, dict[str, int]]] = {}      # device → row → signals
        self._frozen: dict[str, dict[int, dict[str, int]]] = {}
        self._last_row: dict[str, int] = {}
        self._timeouts = 0                                 # follower -1 frames this sweep
        self._sweep_n = 0
        self._sweep_meta: dict | None = None

    @property
    def _scanning(self) -> bool:
        return self._rows > 0 and bool(self._row_ch)

    # ── Ingest: track the sweep, then compose/broadcast as usual ──────────────

    def ingest(self, device_id: str, frame: Frame):
        if self._scanning and device_id in self._row_ch:
            with self._lock:
                payload = self._track_sweep(device_id, frame)
            if payload is not None:
                self._broadcast_frame(payload)             # outside the lock
        return super().ingest(device_id, frame)

    def _track_sweep(self, device_id: str, frame: Frame) -> bytes | None:
        """Accumulate one row frame; return a packed grid when a sweep completes."""
        idx = self._row_ch[device_id]
        samples = frame.samples
        row = int(samples[idx]) if idx < len(samples) else -1
        if not (0 <= row < self._rows):
            self._timeouts += 1                            # follower -1 sentinel (or junk)
            return None

        payload = None
        acc = self._acc.setdefault(device_id, {})
        if row < self._last_row.get(device_id, -1):        # wrapped → this device's sweep done
            if device_id in self._frozen:                  # lapped the stragglers
                payload = self._compose_sweep(force=True)
            self._frozen[device_id] = acc
            acc = self._acc[device_id] = {}
        self._last_row[device_id] = row
        acc[row] = {sig: int(samples[i]) for i, sig in self._dev_cols.get(device_id, [])
                    if i < len(samples)}

        if payload is None and set(self._frozen) >= set(self._row_ch):
            payload = self._compose_sweep()
        return payload

    def _compose_sweep(self, force: bool = False) -> bytes:
        """Pack the frozen per-device sweeps into one rows x cols float32 grid."""
        values: list[float] = []
        lo, hi, missing = math.inf, -math.inf, 0
        for row in range(self._rows):
            for device, signal in self._cols:
                v = self._frozen.get(device, {}).get(row, {}).get(signal)
                if v is None:
                    missing += 1
                    values.append(math.nan)
                else:
                    lo, hi = min(lo, v), max(hi, v)
                    values.append(float(v))
        if missing == len(values):
            lo = hi = 0.0
        self._sweep_n = (self._sweep_n + 1) & 0xFFFFFFFF
        self._sweep_meta = {
            "n": self._sweep_n,
            "rows": self._rows,
            "cols": len(self._cols),
            "complete": missing == 0 and not force,
            "missing_cells": missing,
            "timeouts": self._timeouts,
            "devices": sorted(self._frozen),
        }
        payload = (self._FRAME_HEADER.pack(self._sweep_n, self._rows, len(self._cols), lo, hi)
                   + struct.pack(f"<{len(values)}f", *values))
        self._frozen = {}
        self._timeouts = 0
        return payload

    # ── Interpretation ─────────────────────────────────────────────────────────

    def enrich(self, data: dict, raw: dict[str, int]) -> None:
        kpa: dict[str, float] = {}
        for ch in self.config.channels:
            cal = ch.calibration or {}
            if cal.get("type") == "linear" and ch.signal in raw:
                kpa[ch.signal] = round(
                    to_kpa(raw[ch.signal], float(cal.get("scale", 1.0)),
                           float(cal.get("offset", 0.0))), 3
                )
        if kpa:
            data["kpa"] = kpa
        if self._scanning:
            data["row"] = dict(self._last_row)             # current scan row per device
            if self._sweep_meta:
                data["sweep"] = self._sweep_meta           # grid itself is on the frame lane
