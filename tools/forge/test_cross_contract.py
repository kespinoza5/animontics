"""Unit tests for cross-contract sweep validation (rows/max_code/ack_pins)."""
from __future__ import annotations

import yaml

from tools.forge.contract import load_contract
from tools.forge.cross_contract import cross_contract_issues


def _write_contract(root, stem: str, modules: list[dict]) -> None:
    mcus = root / "config" / "mcus"
    mcus.mkdir(parents=True, exist_ok=True)
    (mcus / f"{stem}.yaml").write_text(yaml.safe_dump({
        "id": stem, "target": "mcu.circuit_python", "board": "xiao_samd21",
        "modules": modules + [{"module": "transport_serial"}],
    }), encoding="utf-8")


def _conductor(rows=16, max_code=65535, ack_pins=("A1", "A2")) -> dict:
    return {"module": "matrix_scan", "rows": rows, "max_code": max_code,
            "ack_pins": list(ack_pins), "dac_pin": "A0"}


def _follower(rows=16, max_code=65535) -> dict:
    return {"module": "scan_follower", "rows": rows, "max_code": max_code,
            "watch_pin": "A1", "ack_pin": "A0"}


def _issues_for(root, stem: str) -> list[str]:
    return cross_contract_issues(load_contract(stem, root), root)


def test_matching_sweep_group_is_clean(tmp_path):
    _write_contract(tmp_path, "cnd", [_conductor()])
    _write_contract(tmp_path, "f1", [_follower()])
    _write_contract(tmp_path, "f2", [_follower()])
    assert _issues_for(tmp_path, "cnd") == []
    assert _issues_for(tmp_path, "f1") == []


def test_rows_mismatch_is_reported_from_either_side(tmp_path):
    _write_contract(tmp_path, "cnd", [_conductor(rows=16, ack_pins=("A1",))])
    _write_contract(tmp_path, "f1", [_follower(rows=8)])
    for stem in ("cnd", "f1"):
        issues = _issues_for(tmp_path, stem)
        assert any("'rows' differs" in i for i in issues), issues


def test_max_code_mismatch_is_reported(tmp_path):
    _write_contract(tmp_path, "cnd", [_conductor(max_code=65535, ack_pins=("A1",))])
    _write_contract(tmp_path, "f1", [_follower(max_code=40000)])
    issues = _issues_for(tmp_path, "cnd")
    assert any("'max_code' differs" in i for i in issues)
    assert any("65535" in i and "40000" in i for i in issues)   # names both values


def test_ack_pin_count_must_match_follower_count(tmp_path):
    _write_contract(tmp_path, "cnd", [_conductor(ack_pins=("A1", "A2", "A3"))])
    _write_contract(tmp_path, "f1", [_follower()])               # only one follower
    issues = _issues_for(tmp_path, "cnd")
    assert any("3 ack_pins but 1 scan_follower" in i for i in issues)


def test_non_scan_contract_never_fails_on_neighbours(tmp_path):
    _write_contract(tmp_path, "cnd", [_conductor(rows=16, ack_pins=("A1",))])
    _write_contract(tmp_path, "f1", [_follower(rows=8)])         # broken group …
    _write_contract(tmp_path, "pwm", [{"module": "pwm_out", "pins": ["D1"]}])
    assert _issues_for(tmp_path, "pwm") == []                    # … unrelated MCU unaffected


def test_unloadable_sibling_is_skipped(tmp_path):
    _write_contract(tmp_path, "cnd", [_conductor(ack_pins=("A1",))])
    _write_contract(tmp_path, "f1", [_follower()])
    (tmp_path / "config" / "mcus" / "broken.yaml").write_text(
        ":not yaml:::", encoding="utf-8")
    assert _issues_for(tmp_path, "cnd") == []


def test_real_lattice_contracts_agree():
    """The actual fleet: featherm4_lattice + samd21_press0/1/2 must be in sync
    (this is the manual-sync warning from the contract headers, automated)."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent.parent
    target = load_contract("featherm4_lattice", root)
    assert cross_contract_issues(target, root) == []
