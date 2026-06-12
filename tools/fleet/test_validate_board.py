"""Unit tests for the deploy-time tier validator (devices/effectors/policies)."""
from __future__ import annotations

from core.models import NodeConfig
from tools.fleet.validate_board import validate_board_tiers

# An injected spec universe so the rules are tested independent of real plugins.
DEVICE_SPECS = {
    "serlink": {"description": "serial", "required": ["port"],
                "optional": ["baud"], "params": []},
    "adc": {"description": "i2c adc", "optional": ["bus", "address"], "params": ["gain"]},
}
EFFECTOR_SPECS = {
    "drive": {"description": "drives via device",
              "backends": {"mcu": ["device"], "sbc": []},
              "default_backend": "mcu", "params": ["min_duty"]},
    "noisemaker": {"description": "no backend", "params": []},
}
POLICY_SPECS = {
    "reflex": {"description": "loop", "needs_effector": True,
               "needs_observation": True, "params": ["gain"]},
}


def _validate(**cfg):
    config = NodeConfig(node_id="n1", node_type="t", **cfg)
    return validate_board_tiers(
        config,
        device_specs=DEVICE_SPECS,
        effector_specs=EFFECTOR_SPECS,
        policy_specs=POLICY_SPECS,
    )


GOOD = dict(
    devices=[{"id": "mcu0", "kind": "serlink", "port": "/dev/ttyACM0"}],
    effectors=[{"id": "fans", "type": "drive", "backend": {"device": "mcu0"}}],
    policies=[{"id": "r1", "type": "reflex", "observation": ["x.y"],
               "action": {"effector": "fans"}}],
)


def test_valid_config_is_clean():
    errors, warnings = _validate(**GOOD)
    assert errors == [] and warnings == []


# ── devices ──────────────────────────────────────────────────────────────────

def test_unknown_device_kind():
    errors, _ = _validate(devices=[{"id": "d", "kind": "nope"}])
    assert any("unknown kind 'nope'" in e for e in errors)


def test_device_missing_required_field():
    errors, _ = _validate(devices=[{"id": "d", "kind": "serlink"}])   # no port
    assert any("missing required 'port'" in e for e in errors)


def test_device_unknown_param_is_warning_not_error():
    errors, warnings = _validate(
        devices=[{"id": "d", "kind": "adc", "params": {"gian": 2}}])  # typo'd gain
    assert errors == []
    assert any("unknown param 'gian'" in w for w in warnings)


def test_duplicate_ids_are_errors():
    errors, _ = _validate(devices=[
        {"id": "d", "kind": "adc"}, {"id": "d", "kind": "adc"}])
    assert any("duplicate id" in e for e in errors)


# ── effectors ────────────────────────────────────────────────────────────────

def test_unknown_effector_type():
    errors, _ = _validate(effectors=[{"id": "e", "type": "nope"}])
    assert any("unknown type 'nope'" in e for e in errors)


def test_effector_backend_device_must_be_declared():
    errors, _ = _validate(
        effectors=[{"id": "e", "type": "drive", "backend": {"device": "ghost"}}])
    assert any("backend.device 'ghost'" in e for e in errors)


def test_effector_default_backend_requires_its_keys():
    # No kind → default "mcu" → device required.
    errors, _ = _validate(effectors=[{"id": "e", "type": "drive"}])
    assert any("requires 'device'" in e for e in errors)


def test_effector_alternate_backend_ok_without_device():
    errors, _ = _validate(
        effectors=[{"id": "e", "type": "drive", "backend": {"kind": "sbc"}}])
    assert errors == []


def test_effector_invalid_backend_kind():
    errors, _ = _validate(
        effectors=[{"id": "e", "type": "drive", "backend": {"kind": "warp"}}])
    assert any("backend kind 'warp'" in e for e in errors)


def test_disabled_effector_is_skipped():
    errors, _ = _validate(effectors=[{"id": "e", "type": "nope", "enabled": False}])
    assert errors == []


# ── policies ─────────────────────────────────────────────────────────────────

def test_policy_needs_effector():
    errors, _ = _validate(policies=[
        {"id": "p", "type": "reflex", "observation": ["x"]}])
    assert any("action.effector is required" in e for e in errors)


def test_policy_effector_must_be_declared_and_enabled():
    cfg = dict(GOOD)
    cfg["effectors"] = [{"id": "fans", "type": "drive",
                         "backend": {"device": "mcu0"}, "enabled": False}]
    errors, _ = _validate(**cfg)
    assert any("'fans' is not a declared enabled effector" in e for e in errors)


def test_policy_empty_observation_is_warning():
    cfg = dict(GOOD)
    cfg["policies"] = [{"id": "p", "type": "reflex", "action": {"effector": "fans"}}]
    errors, warnings = _validate(**cfg)
    assert errors == []
    assert any("observation list is empty" in w for w in warnings)


# ── sensors' device references ───────────────────────────────────────────────

def test_sensor_devices_must_be_declared():
    errors, _ = _validate(sensors=[
        {"id": "s", "type": "mq_array", "devices": ["ghost"]}])
    assert any("devices entry 'ghost'" in e for e in errors)


def test_sensor_channel_device_must_be_declared():
    errors, _ = _validate(sensors=[
        {"id": "s", "type": "pressure_array",
         "channels": [{"index": 0, "signal": "p0", "device": "ghost"}]}])
    assert any("channel 'p0' reads device 'ghost'" in e for e in errors)


# ── against the real registries ──────────────────────────────────────────────

def test_real_registry_happy_path():
    """A realistic board config passes against the live plugin SPECs."""
    config = NodeConfig(
        node_id="n1", node_type="t",
        devices=[{"id": "lxiao", "kind": "mcu_serial", "port": "/dev/ttyACM0"}],
        effectors=[{"id": "fans", "type": "fan_array",
                    "backend": {"device": "lxiao"},
                    "channels": [{"name": "intake", "index": 0}]}],
        policies=[{"id": "reflex", "type": "curve", "always_on": True,
                   "observation": ["board_temp.cpu_c"],
                   "action": {"effector": "fans"},
                   "params": {"in_min": [40], "in_max": [70]}}],
    )
    errors, warnings = validate_board_tiers(config)
    assert errors == [] and warnings == []


def test_real_registry_catches_the_classic_mistakes():
    """The TODO's motivating examples: sara_r5 with no port, ghost device ref."""
    config = NodeConfig(
        node_id="n1", node_type="t",
        devices=[{"id": "modem", "kind": "sara_r5"}],                  # no port
        effectors=[{"id": "fans", "type": "fan_array",
                    "backend": {"device": "lxiao"}}],                  # ghost device
    )
    errors, _ = validate_board_tiers(config)
    assert any("missing required 'port'" in e for e in errors)
    assert any("backend.device 'lxiao'" in e for e in errors)
