"""Unit tests for the deploy-time reconciliation logic (desired state ⇄ board wiring)."""
from __future__ import annotations

import pytest

from core.models import (
    AnimonNodeEntry,
    AnimonSensorRef,
    ConnectionConfig,
    NodeConfig,
    SensorConfig,
)
from tools.fleet.reconcile import (
    ReconcileError,
    _default_connection,
    reconcile,
    validate_connection,
)

# A minimal METADATA universe for the tests — one UART type, one I2C type.
METADATA = {
    "fake_uart": {
        "type": "fake_uart",
        "connection": {
            "supported": ["uart"],
            "defaults": {"baud_rate": 115200},
            "valid": {"baud_rate": [115200]},
        },
    },
    "fake_i2c": {
        "type": "fake_i2c",
        "connection": {
            "supported": ["i2c"],
            "defaults": {"bus": 1, "address": 0x29},
            "valid": {"address": [0x29]},
        },
    },
}


def _entry(*sensors: tuple[str, str], port: int = 8080) -> AnimonNodeEntry:
    return AnimonNodeEntry(
        id="n1",
        type="orangepi_zero2",
        sensors=[AnimonSensorRef(id=i, type=t) for i, t in sensors],
        port=port,
    )


def _board(*sensors: SensorConfig) -> NodeConfig:
    return NodeConfig(node_id="n1", node_type="orangepi_zero2", sensors=list(sensors))


# ── _default_connection ───────────────────────────────────────────────────────

def test_default_connection_uses_metadata_defaults():
    conn = _default_connection("fake_uart", METADATA)
    assert conn.type == "uart"
    assert conn.baud_rate == 115200


def test_default_connection_none_without_metadata():
    assert _default_connection("mystery", METADATA) is None


def test_default_connection_prefers_uart_over_i2c():
    meta = {"multi": {"connection": {"supported": ["i2c", "uart"], "defaults": {}}}}
    assert _default_connection("multi", meta).type == "uart"


# ── validate_connection ───────────────────────────────────────────────────────

def test_validate_rejects_unsupported_type():
    errs = validate_connection(
        "fake_uart", ConnectionConfig(type="i2c", bus=1, address=0x29), METADATA
    )
    assert any("not supported" in e for e in errs)


def test_validate_rejects_bad_baud_and_address():
    errs = validate_connection(
        "fake_uart", ConnectionConfig(type="uart", baud_rate=9600), METADATA
    )
    assert any("baud_rate 9600" in e for e in errs)
    errs = validate_connection(
        "fake_i2c", ConnectionConfig(type="i2c", bus=1, address=0x30), METADATA
    )
    assert any("0x30" in e for e in errs)


def test_validate_passes_clean_config_and_unknown_type():
    assert validate_connection(
        "fake_uart", ConnectionConfig(type="uart", baud_rate=115200), METADATA
    ) == []
    # No metadata → nothing to validate against, not an error.
    assert validate_connection(
        "mystery", ConnectionConfig(type="uart", baud_rate=42), METADATA
    ) == []


# ── reconcile ────────────────────────────────────────────────────────────────

def test_existing_wiring_is_kept_verbatim():
    existing = SensorConfig(
        id="s1", type="fake_uart",
        connection=ConnectionConfig(type="uart", port="/dev/ttyS3", baud_rate=115200),
    )
    new, changes = reconcile(_entry(("s1", "fake_uart")), _board(existing), METADATA)
    assert new.sensors == [existing]
    assert changes == []


def test_new_sensor_added_with_metadata_defaults():
    new, changes = reconcile(_entry(("s1", "fake_uart")), _board(), METADATA)
    [sc] = new.sensors
    assert sc.connection.type == "uart"
    assert sc.connection.baud_rate == 115200
    assert any("added with default connection" in c for c in changes)


def test_new_sensor_without_metadata_raises():
    with pytest.raises(ReconcileError, match="no METADATA defaults"):
        reconcile(_entry(("s1", "mystery")), _board(), METADATA)


def test_removed_sensor_is_disabled_not_deleted():
    existing = SensorConfig(
        id="old", type="fake_uart",
        connection=ConnectionConfig(type="uart", baud_rate=115200),
    )
    new, changes = reconcile(_entry(), _board(existing), METADATA)
    [sc] = new.sensors
    assert sc.id == "old" and sc.enabled is False
    assert any("disabled" in c for c in changes)


def test_disabled_sensor_is_reenabled_when_desired():
    existing = SensorConfig(
        id="s1", type="fake_uart", enabled=False,
        connection=ConnectionConfig(type="uart", baud_rate=115200),
    )
    new, changes = reconcile(_entry(("s1", "fake_uart")), _board(existing), METADATA)
    assert new.sensors[0].enabled is True
    assert any("re-enabled" in c for c in changes)


def test_type_change_keeps_connection_and_warns():
    existing = SensorConfig(
        id="s1", type="fake_uart",
        connection=ConnectionConfig(type="uart", port="/dev/ttyS3", baud_rate=115200),
    )
    new, changes = reconcile(_entry(("s1", "fake_i2c")), _board(existing), METADATA)
    [sc] = new.sensors
    assert sc.type == "fake_i2c"
    assert sc.connection.port == "/dev/ttyS3"     # wiring kept
    assert any("type changed" in c for c in changes)


def test_invalid_kept_wiring_surfaces_validation_warning():
    existing = SensorConfig(
        id="s1", type="fake_uart",
        connection=ConnectionConfig(type="uart", baud_rate=9600),  # not a valid baud
    )
    _, changes = reconcile(_entry(("s1", "fake_uart")), _board(existing), METADATA)
    assert any("VALIDATION WARNING" in c for c in changes)


def test_fresh_board_projects_network_from_access_port():
    new, changes = reconcile(_entry(("s1", "fake_uart"), port=9191), None, METADATA,
                             node_type="raspberry_pi_5")
    assert new.node_id == "n1"
    assert new.node_type == "raspberry_pi_5"
    assert new.network.host == "0.0.0.0"
    assert new.network.port == 9191
    assert any("new config" in c for c in changes)


def test_fresh_board_preserves_other_tiers_absent():
    new, _ = reconcile(_entry(("s1", "fake_uart")), None, METADATA)
    assert new.devices == [] and new.effectors == [] and new.policies == []


def test_existing_board_other_tiers_untouched():
    """Reconcile only negotiates sensors — devices/effectors/policies pass through."""
    board = NodeConfig(
        node_id="n1", node_type="x",
        sensors=[],
        devices=[{"id": "mcu0", "kind": "mcu_serial", "port": "/dev/ttyACM0"}],
        effectors=[{"id": "fans", "type": "fan_array"}],
        policies=[{"id": "reflex", "type": "curve"}],
    )
    new, _ = reconcile(_entry(("s1", "fake_uart")), board, METADATA)
    assert [d.id for d in new.devices] == ["mcu0"]
    assert [e.id for e in new.effectors] == ["fans"]
    assert [p.id for p in new.policies] == ["reflex"]
