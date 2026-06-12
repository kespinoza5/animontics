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


# ── effector → MCU contract channel cross-check ───────────────────────────────

def _mcu_project(tmp_path):
    """Minimal project tree: one CP contract with a 2-pin pwm_out."""
    (tmp_path / "config" / "mcus").mkdir(parents=True)
    (tmp_path / "config" / "mcus" / "mcu0.yaml").write_text(
        """
id: mcu0
target: mcu.circuit_python
board: xiao_rp2040
modules:
  - {module: pwm_out, pins: [D1, D2]}
  - {module: transport_serial}
""", encoding="utf-8")
    mods = tmp_path / "mcu" / "circuit_python" / "modules"
    (mods / "pwm_out").mkdir(parents=True)
    (mods / "pwm_out" / "manifest.yaml").write_text(
        "module: pwm_out\naccepts:\n  set_duty: {channel: int, duty: int}\n",
        encoding="utf-8")
    (mods / "transport_serial").mkdir()
    (mods / "transport_serial" / "manifest.yaml").write_text(
        "module: transport_serial\nrole: transport\n", encoding="utf-8")
    return tmp_path


MCU_EFFECTOR_SPECS = {
    "drive": {"backends": {"mcu": ["device"]}, "default_backend": "mcu",
              "mcu_command": "set_duty", "params": []},
    "mover": {"backends": {"mcu": ["device"]}, "default_backend": "mcu",
              "mcu_command": "set_us", "params": []},
}


def _validate_mcu(tmp_path, effector):
    config = NodeConfig(
        node_id="n1", node_type="t",
        devices=[{"id": "mcu0", "kind": "serlink", "port": "/dev/ttyACM0"}],
        effectors=[effector],
    )
    return validate_board_tiers(
        config, device_specs=DEVICE_SPECS, effector_specs=MCU_EFFECTOR_SPECS,
        policy_specs=POLICY_SPECS, project_root=_mcu_project(tmp_path),
    )


def test_mcu_channels_in_range_pass(tmp_path):
    errors, warnings = _validate_mcu(tmp_path, {
        "id": "fans", "type": "drive", "backend": {"device": "mcu0"},
        "channels": [{"name": "a", "index": 0}, {"name": "b", "index": 1}]})
    assert errors == [] and warnings == []


def test_mcu_channel_index_out_of_range(tmp_path):
    errors, _ = _validate_mcu(tmp_path, {
        "id": "fans", "type": "drive", "backend": {"device": "mcu0"},
        "channels": [{"name": "c", "index": 2}]})        # only 2 set_duty slots
    assert any("channel index 2 out of range" in e and "2 'set_duty'" in e
               for e in errors)


def test_mcu_command_not_accepted_by_contract(tmp_path):
    errors, _ = _validate_mcu(tmp_path, {
        "id": "neck", "type": "mover", "backend": {"device": "mcu0"},
        "channels": [{"name": "tilt", "index": 0}]})     # no servo_out on mcu0
    assert any("no module accepting 'set_us'" in e for e in errors)


def test_mcu_backend_channel_key_checked(tmp_path):
    # power_rail-style single backend channel index
    errors, _ = _validate_mcu(tmp_path, {
        "id": "rail", "type": "drive",
        "backend": {"kind": "mcu", "device": "mcu0", "channel": 5}})
    assert any("channel index 5 out of range" in e for e in errors)


def test_missing_contract_is_warning_not_error(tmp_path):
    root = _mcu_project(tmp_path)
    config = NodeConfig(
        node_id="n1", node_type="t",
        devices=[{"id": "ghostmcu", "kind": "serlink", "port": "/dev/x"}],
        effectors=[{"id": "fans", "type": "drive",
                    "backend": {"device": "ghostmcu"},
                    "channels": [{"name": "a", "index": 0}]}],
    )
    errors, warnings = validate_board_tiers(
        config, device_specs=DEVICE_SPECS, effector_specs=MCU_EFFECTOR_SPECS,
        policy_specs=POLICY_SPECS, project_root=root)
    assert errors == []
    assert any("no contract config/mcus/ghostmcu.yaml" in w for w in warnings)
