"""Unit tests for pressure_array — transfer math + multi-device compose (no hardware)."""
from __future__ import annotations

import math
import struct

import pytest

from core.mcu_link import FrameStream, encode
from core.models import SensorChannel, SensorConfig
from sensors.pressure_array.driver import to_kpa
from sensors.pressure_array.sensor import PressureArray


def test_to_kpa_linear():
    assert to_kpa(1000, 0.1, -5.0) == pytest.approx(95.0)


def _sensor(channels):
    return PressureArray("cp", SensorConfig(id="cp", type="pressure_array", channels=channels))


def test_aggregates_across_devices_with_kpa():
    s = _sensor([
        SensorChannel(index=0, signal="cp_00", device="press0",
                      calibration={"type": "linear", "scale": 0.1, "offset": 0.0}),
        SensorChannel(index=1, signal="cp_01", device="press0"),                 # raw only
        SensorChannel(index=0, signal="cp_16", device="press1",
                      calibration={"type": "linear", "scale": 0.2, "offset": 0.0}),
    ])
    s.ingest("press0", FrameStream().feed(encode([300, 400], seq=1))[0])
    reading = s.ingest("press1", FrameStream().feed(encode([500], seq=2))[0])
    assert reading.data["raw"] == {"cp_00": 300, "cp_01": 400, "cp_16": 500}
    assert reading.data["kpa"] == {"cp_00": 30.0, "cp_16": 100.0}   # only calibrated channels
    assert "sweep" not in reading.data           # flat array: no scan machinery


# ── Scanned-lattice composition (row_tag channels + params.rows) ──────────────

def _frame(samples, seq=0):
    return FrameStream().feed(encode(samples, seq=seq))[0]


def _lattice(rows=2):
    """Two devices, two rows: channel 0 = row tag, then two columns each."""
    channels = []
    for dev, p in (("cnd", "c"), ("ant", "a")):
        channels.append(SensorChannel(index=0, signal=f"{p}_row", device=dev,
                                      calibration={"type": "row_tag"}))
        channels += [SensorChannel(index=1, signal=f"{p}0", device=dev),
                     SensorChannel(index=2, signal=f"{p}1", device=dev)]
    cfg = SensorConfig(id="lat", type="pressure_array", channels=channels,
                       params={"rows": rows})
    return PressureArray("lat", cfg)


def test_sweep_composes_on_all_devices_wrapping():
    s = _lattice(rows=2)
    q = s.subscribe_frames()
    # both devices deliver rows 0 and 1, then wrap to row 0 → sweep emitted
    s.ingest("cnd", _frame([0, 10, 11]))
    s.ingest("ant", _frame([0, 20, 21]))
    s.ingest("cnd", _frame([1, 12, 13]))
    s.ingest("ant", _frame([1, 22, 23]))
    s.ingest("cnd", _frame([0, 10, 11]))     # cnd wraps → frozen
    assert q.empty()                          # ant not wrapped yet
    reading = s.ingest("ant", _frame([0, 20, 21]))   # ant wraps → compose
    payload = q.get_nowait()
    n, rows, cols, lo, hi = struct.unpack_from("<IHHff", payload)
    assert (n, rows, cols) == (1, 2, 4)
    assert (lo, hi) == (10.0, 23.0)
    grid = struct.unpack_from("<8f", payload, 16)
    # row-major, columns in config order: c0 c1 a0 a1
    assert grid == (10.0, 11.0, 20.0, 21.0, 12.0, 13.0, 22.0, 23.0)
    assert reading.data["sweep"]["complete"] is True
    assert reading.data["sweep"]["missing_cells"] == 0
    assert reading.data["row"] == {"cnd": 0, "ant": 0}


def test_follower_timeout_sentinel_counted_not_stored():
    s = _lattice(rows=2)
    s.ingest("ant", _frame([-1, 99, 99]))     # follower lost the conductor
    s.ingest("ant", _frame([0, 20, 21]))
    assert s.latest.data["row"] == {"ant": 0}  # the -1 frame never became a row
    # the timeout surfaces in the next sweep summary
    s.ingest("cnd", _frame([0, 10, 11]))
    s.ingest("cnd", _frame([1, 12, 13]))
    s.ingest("ant", _frame([1, 22, 23]))
    s.ingest("cnd", _frame([0, 0, 0]))
    r = s.ingest("ant", _frame([0, 0, 0]))
    assert r.data["sweep"]["timeouts"] == 1


def test_lapping_device_forces_partial_sweep():
    s = _lattice(rows=2)
    q = s.subscribe_frames()
    # only cnd delivers; ant is dead. cnd completes two sweeps.
    s.ingest("cnd", _frame([0, 10, 11]))
    s.ingest("cnd", _frame([1, 12, 13]))
    s.ingest("cnd", _frame([0, 14, 15]))      # wrap 1 → frozen, waiting for ant
    s.ingest("cnd", _frame([1, 16, 17]))
    reading = s.ingest("cnd", _frame([0, 18, 19]))   # wrap 2 → force partial emit
    payload = q.get_nowait()
    _, rows, cols, _, _ = struct.unpack_from("<IHHff", payload)
    assert (rows, cols) == (2, 4)
    grid = struct.unpack_from("<8f", payload, 16)
    assert grid[0:2] == (10.0, 11.0) and math.isnan(grid[2]) and math.isnan(grid[3])
    sweep = reading.data["sweep"]
    assert sweep["complete"] is False
    assert sweep["missing_cells"] == 4        # ant's 2 cols x 2 rows
    assert sweep["devices"] == ["cnd"]
