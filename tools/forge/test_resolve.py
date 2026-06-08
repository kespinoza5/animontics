"""Unit tests for channel resolution — derive node channels from contracts."""
from __future__ import annotations

from pathlib import Path

from tools.forge.resolve import derive_sensor_channels, resolve_board

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # uses config/mcus/example.yaml


def test_derive_from_contract():
    chans = derive_sensor_channels(["example"], PROJECT_ROOT)
    assert [c.signal for c in chans] == ["example_0", "example_1", "example_2", "example_3"]
    assert all(c.device == "example" for c in chans)
    assert [c.index for c in chans] == [0, 1, 2, 3]


def test_resolve_board_fills_device_fed_sensor():
    board = {"sensors": [
        {"id": "arr", "type": "analog_in", "devices": ["example"]},
        {"id": "scalar", "type": "tf_mini"},          # no devices → untouched
    ]}
    board, n = resolve_board(board, PROJECT_ROOT)
    assert n == 1
    chans = board["sensors"][0]["channels"]
    assert len(chans) == 4
    assert chans[0]["signal"] == "example_0" and chans[0]["device"] == "example"
    assert "channels" not in board["sensors"][1]


def test_explicit_channels_win():
    board = {"sensors": [{"id": "arr", "type": "a", "devices": ["example"],
                          "channels": [{"index": 0, "signal": "keep"}]}]}
    board, n = resolve_board(board, PROJECT_ROOT)
    assert n == 0                                     # already authored → not overwritten
    assert board["sensors"][0]["channels"][0]["signal"] == "keep"
