"""Unit tests for the config loaders — fleet merge, board configs, overrides."""
import pytest

from core.config import (
    _merge,
    clear_board_override,
    load_board_override,
    load_board_staging,
    load_fleet,
    load_node_config,
    save_board_override,
    save_board_staging,
)
from core.models import AnimonNodeAccess, NodeConfig, NodeDesiredState, SensorConfig


def test_hostname_and_port_come_from_access():
    desired = NodeDesiredState(id="n1", type="orangepi_zero2", role="proprioception")
    access = AnimonNodeAccess(ip="192.168.1.140", hostname="orangepi",
                              port=9090, ssh_user="orangepi")
    entry = _merge(desired, access)
    # Address is authored in the access layer, not desired state.
    assert entry.hostname == "orangepi"
    assert entry.port == 9090
    assert entry.ip == "192.168.1.140"
    # Desired-state fields still come from desired state.
    assert entry.role == "proprioception"


def test_port_defaults_to_8080_when_unset():
    entry = _merge(
        NodeDesiredState(id="n2", type="raspberry_pi_5"),
        AnimonNodeAccess(ip="192.168.1.10"),
    )
    assert entry.port == 8080
    assert entry.hostname is None


def test_desired_state_has_no_network_fields():
    # Desired state is pure logic — the address fields were removed from the model.
    fields = NodeDesiredState.model_fields
    assert "hostname" not in fields
    assert "port" not in fields


# ── load_node_config ─────────────────────────────────────────────────────────

def test_load_node_config_missing_file_is_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Board config not found"):
        load_node_config(tmp_path / "nope.yaml")


def test_load_node_config_parses_all_tiers(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        """
node_id: n1
node_type: orangepi_zero2
network: {host: 0.0.0.0, port: 9090}
devices:
  - {id: mcu0, kind: mcu_serial, port: /dev/ttyACM0, baud: 115200}
sensors:
  - {id: s1, type: tf_mini, connection: {type: uart, port: /dev/ttyS3, baud_rate: 115200}}
effectors:
  - {id: fans, type: fan_array, backend: {device: mcu0}}
policies:
  - {id: reflex, type: curve, always_on: true}
""",
        encoding="utf-8",
    )
    cfg = load_node_config(p)
    assert cfg.network.port == 9090
    assert cfg.devices[0].kind == "mcu_serial"
    assert cfg.sensors[0].connection.baud_rate == 115200
    assert cfg.effectors[0].backend["device"] == "mcu0"
    assert cfg.policies[0].always_on is True


# ── board staging round-trip ─────────────────────────────────────────────────

def _node_config() -> NodeConfig:
    return NodeConfig(
        node_id="n1", node_type="x",
        sensors=[SensorConfig(id="s1", type="tf_mini",
                              connection={"type": "uart", "baud_rate": 115200})],
    )


def test_board_staging_round_trip(tmp_path):
    assert load_board_staging("n1", tmp_path) is None      # nothing staged yet
    path = save_board_staging("n1", _node_config(), tmp_path)
    assert path == tmp_path / "config" / "boards" / "n1.yaml"
    loaded = load_board_staging("n1", tmp_path)
    assert loaded == _node_config()


# ── override markers ─────────────────────────────────────────────────────────

def test_override_round_trip_and_clear(tmp_path):
    assert load_board_override("n1", tmp_path) is None
    save_board_override("n1", _node_config(), tmp_path,
                        source="adhoc.yaml", note="testing")
    marker = load_board_override("n1", tmp_path)
    assert marker.note == "testing"
    assert marker.source == "adhoc.yaml"
    assert marker.config == _node_config()
    assert marker.deployed_at                      # timestamp recorded
    assert clear_board_override("n1", tmp_path) is True
    assert load_board_override("n1", tmp_path) is None
    assert clear_board_override("n1", tmp_path) is False   # idempotent


def test_override_does_not_touch_staging_baseline(tmp_path):
    save_board_staging("n1", _node_config(), tmp_path)
    baseline = (tmp_path / "config" / "boards" / "n1.yaml").read_text(encoding="utf-8")
    save_board_override("n1", _node_config(), tmp_path, note="x")
    assert (tmp_path / "config" / "boards" / "n1.yaml").read_text(encoding="utf-8") == baseline


# ── load_fleet ───────────────────────────────────────────────────────────────

def test_load_fleet_missing_nodes_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="desired-state directory"):
        load_fleet(tmp_path)


def test_load_fleet_merges_access_and_skips_example(tmp_path):
    nodes = tmp_path / "config" / "nodes"
    nodes.mkdir(parents=True)
    (nodes / "n1.yaml").write_text(
        "id: n1\ntype: orangepi_zero2\nsensors: [{id: s1, type: tf_mini}]\n",
        encoding="utf-8",
    )
    (nodes / "example.yaml").write_text("id: example\ntype: t\n", encoding="utf-8")
    (tmp_path / "config" / "animon.yaml").write_text(
        """
system_name: bench
nodes:
  n1: {ip: 192.168.1.50, port: 9090, ssh_user: pi}
""",
        encoding="utf-8",
    )
    fleet = load_fleet(tmp_path)
    assert fleet.system_name == "bench"
    assert [n.id for n in fleet.nodes] == ["n1"]   # example.yaml skipped
    n1 = fleet.nodes[0]
    assert n1.ip == "192.168.1.50" and n1.port == 9090 and n1.ssh_user == "pi"
    assert n1.sensors[0].type == "tf_mini"


def test_load_fleet_access_layer_optional(tmp_path):
    nodes = tmp_path / "config" / "nodes"
    nodes.mkdir(parents=True)
    (nodes / "n1.yaml").write_text("id: n1\ntype: t\n", encoding="utf-8")
    fleet = load_fleet(tmp_path)        # no animon.yaml at all
    assert fleet.nodes[0].ip is None    # access fields default to None
