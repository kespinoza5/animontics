"""Integration tests for the node app — lifespan startup + the core HTTP surface.

Runs the real create_app() + lifespan against a temp config.yaml and fake
sensor types registered just for the test. Locks in two contracts:

  • routers read request.app.state (sensors/devices/effectors/policies/relay) —
    never module-level registries;
  • startup degrades per-plugin: an unknown type or a driver that raises at
    start() loses that plugin only, never the node.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import node.app as node_app
from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase


@register("_apptest")
class _FakeSensor(SensorBase):
    """Healthy fake that has one reading available immediately."""

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        self._reading: SensorReading | None = None

    def start(self) -> None:
        self._reading = SensorReading(
            sensor_id=self.id, sensor_type="_apptest",
            timestamp=time.time(), data={"distance_mm": 123},
        )

    def stop(self) -> None: ...

    @property
    def latest(self) -> SensorReading | None:
        return self._reading

    def is_healthy(self) -> bool:
        return True


@register("_apptest_boom")
class _BoomSensor(_FakeSensor):
    """Driver that blows up at start() — must degrade, not kill the node."""

    def start(self) -> None:
        raise RuntimeError("dead bus")


CONFIG = """
node_id: testnode
node_type: bench
sensors:
  - {id: s1, type: _apptest}
  - {id: s_boom, type: _apptest_boom}
  - {id: s_unknown, type: not_a_real_type}
  - {id: s_off, type: _apptest, enabled: false}
"""


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    cfg = tmp_path_factory.mktemp("cfg") / "config.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")
    original = node_app._CONFIG_PATH
    node_app._CONFIG_PATH = str(cfg)
    try:
        with TestClient(node_app.create_app()) as c:
            yield c
    finally:
        node_app._CONFIG_PATH = original


# ── startup behavior ─────────────────────────────────────────────────────────

def test_only_startable_enabled_sensors_survive(client):
    info = client.get("/").json()
    assert info["node_id"] == "testnode"
    ids = [s["id"] for s in info["sensors"]]
    assert ids == ["s1"]            # boom degraded, unknown degraded, off skipped
    assert info["sensors"][0]["healthy"] is True


# ── sensor routes ────────────────────────────────────────────────────────────

def test_list_sensors_reads_app_state(client):
    [entry] = client.get("/sensors").json()
    assert entry == {"id": "s1", "type": "_apptest", "enabled": True}


def test_get_sensor_latest_reading(client):
    body = client.get("/sensors/s1").json()
    assert body["sensor_id"] == "s1"
    assert body["data"] == {"distance_mm": 123}


def test_get_unknown_sensor_404(client):
    assert client.get("/sensors/nope").status_code == 404


def test_ws_sends_latest_reading_immediately(client):
    with client.websocket_connect("/sensors/s1/ws") as ws:
        import json
        msg = json.loads(ws.receive_text())
        assert msg["data"]["distance_mm"] == 123


def test_ws_unknown_sensor_closes_4004(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/sensors/nope/ws"):
            pass
    assert exc.value.code == 4004


def test_frames_rejected_for_non_frame_sensor(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/sensors/s1/frames"):
            pass
    assert exc.value.code == 4003


# ── other tiers' surfaces exist and read app.state ───────────────────────────

def test_devices_effectors_policies_empty_lists(client):
    assert client.get("/devices").json() == []
    assert client.get("/effectors").json() == []
    assert client.get("/policies").json() == []
    assert client.get("/devices/nope").status_code == 404
    assert client.get("/effectors/nope").status_code == 404
    assert client.get("/policies/nope").status_code == 404
