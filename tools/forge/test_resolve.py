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


# ── resolve_node_config (the NodeConfig twin animon deploy calls) ─────────────

def test_resolve_node_config_fills_models_in_place():
    from core.models import NodeConfig
    from tools.forge.resolve import resolve_node_config

    config = NodeConfig(node_id="n1", node_type="t", sensors=[
        {"id": "arr", "type": "analog_in", "devices": ["example"]},
        {"id": "scalar", "type": "tf_mini"},
        {"id": "authored", "type": "analog_in", "devices": ["example"],
         "channels": [{"index": 0, "signal": "keep"}]},
        {"id": "off", "type": "analog_in", "devices": ["example"], "enabled": False},
    ])
    notes = resolve_node_config(config, PROJECT_ROOT)

    assert len(notes) == 1 and "arr" in notes[0]
    arr = config.sensors[0]
    assert [c.signal for c in arr.channels] == [
        "example_0", "example_1", "example_2", "example_3"]
    assert all(c.device == "example" for c in arr.channels)
    assert config.sensors[1].channels == []                    # scalar untouched
    assert config.sensors[2].channels[0].signal == "keep"      # authored wins
    assert config.sensors[3].channels == []                    # disabled skipped


def test_resolve_node_config_missing_contract_raises():
    import pytest
    from core.models import NodeConfig
    from tools.forge.contract import ContractError
    from tools.forge.resolve import resolve_node_config

    config = NodeConfig(node_id="n1", node_type="t", sensors=[
        {"id": "arr", "type": "analog_in", "devices": ["no_such_contract"]}])
    with pytest.raises(ContractError):
        resolve_node_config(config, PROJECT_ROOT)


def test_resolve_node_config_warns_on_channel_less_contract(tmp_path):
    """A device-fed sensor pointed at a contract with no channels block gets a
    warning note and stays empty (lxiao tach case) — never a silent '0 resolved'."""
    import yaml
    from core.models import NodeConfig
    from tools.forge.resolve import resolve_node_config

    mcus = tmp_path / "config" / "mcus"
    mcus.mkdir(parents=True)
    (mcus / "bare.yaml").write_text(yaml.safe_dump({
        "id": "bare", "target": "mcu.circuit_python", "board": "xiao_samd21",
        "modules": [{"module": "transport_serial"}],
    }), encoding="utf-8")

    config = NodeConfig(node_id="n1", node_type="t", sensors=[
        {"id": "arr", "type": "fan_tach", "devices": ["bare"]}])
    notes = resolve_node_config(config, tmp_path)
    assert config.sensors[0].channels == []
    assert len(notes) == 1 and "declare no channels" in notes[0]
