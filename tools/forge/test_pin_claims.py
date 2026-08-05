"""Unit tests for pin-capability claims — manifest param→kind maps vs board tables."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.forge.contract import McuTarget, validate

_ROOT = Path(__file__).resolve().parent.parent.parent
_FLEET = ("featherm4_lattice", "samd21_press0", "samd21_cervical")


def _absent(*stems: str) -> list[str]:
    """Which of these contracts are missing. config/mcus/ is gitignored, so the
    real-fleet test below only runs on a machine that has the fleet checked
    out — in a clean clone it skips rather than fails."""
    return [s for s in stems
            if not (_ROOT / "config" / "mcus" / f"{s}.yaml").exists()]

PLATFORM = {
    "boards": {
        "tabled": {
            "board": "cp_tabled",
            "pins": {
                "gpio":    ["D1", "D2", "D3", "D4"],
                "adc":     ["A1", "A2"],
                "dac":     ["A0"],
                "pwm":     ["D1", "D2"],
                "countio": ["D1", "D3"],
                "uart":    {"tx": ["D1"], "rx": ["D2"]},
            },
        },
        "bare": {"board": "cp_bare"},          # no pin tables at all
    },
    # family-level fallback (the arduino pattern)
    "pins": {"adc": ["A9"]},
}

MANIFESTS = {
    "transport_serial": {"module": "transport_serial",
                         "platforms": ["circuit_python"], "role": "transport"},
    "pwm_out": {"module": "pwm_out", "platforms": ["circuit_python"],
                "role": "actuator", "claims": {"pins": "pwm"}},
    "tach": {"module": "tach", "platforms": ["circuit_python"],
             "role": "sensor", "claims": {"pins": "countio"}},
    "scanner": {"module": "scanner", "platforms": ["circuit_python"], "role": "sensor",
                "claims": {"pins": "gpio", "dac_pin": "dac", "ack_pins": "adc"}},
    "uplink": {"module": "uplink", "platforms": ["circuit_python"], "role": "sensor",
               "claims": {"tx_pin": "uart.tx"}},
    "unclaimed": {"module": "unclaimed", "platforms": ["circuit_python"], "role": "sensor"},
}


def _target(modules: list[dict], board: str = "tabled") -> McuTarget:
    modules = modules + [{"module": "transport_serial"}]
    return McuTarget(id="t", target="mcu.circuit_python", board=board, modules=modules)


def _errors(modules: list[dict], board: str = "tabled") -> list[str]:
    return validate(_target(modules, board), PLATFORM, MANIFESTS)


def test_valid_claims_pass():
    assert _errors([{"module": "pwm_out", "pins": ["D1", "D2"]},
                    {"module": "scanner", "pins": ["D3", "D4"],
                     "dac_pin": "A0", "ack_pins": ["A1", "A2"]}]) == []


def test_capability_miss_on_pins_list():
    errs = _errors([{"module": "tach", "pins": ["D1", "D2"]}])
    assert any("D2 is not a valid countio pin" in e for e in errs)
    assert not any("D1 " in e for e in errs)


def test_capability_miss_on_scalar_param():
    errs = _errors([{"module": "scanner", "pins": ["D1"], "dac_pin": "A1"}])
    assert any("A1 is not a valid dac pin" in e for e in errs)


def test_dotted_role_kind():
    assert _errors([{"module": "uplink", "tx_pin": "D1"}]) == []
    errs = _errors([{"module": "uplink", "tx_pin": "D2"}])   # D2 is rx, not tx
    assert any("D2 is not a valid uart.tx pin" in e for e in errs)


def test_cross_param_conflict_within_module():
    errs = _errors([{"module": "scanner", "pins": ["D1"],
                     "dac_pin": "A0", "ack_pins": ["A1"],
                     "watch": None}])
    assert errs == []                                         # sanity: distinct pins fine
    errs = _errors([{"module": "scanner", "pins": ["D1"],
                     "dac_pin": "A0", "ack_pins": ["A0"]}])   # A0 reused (dac+adc!)
    assert any("claimed twice by 'scanner'" in e for e in errs)


def test_cross_module_conflict_includes_param_pins():
    errs = _errors([{"module": "pwm_out", "pins": ["D1"]},
                    {"module": "scanner", "pins": ["D2"], "dac_pin": "A0",
                     "ack_pins": ["A1"]},
                    {"module": "tach", "pins": ["D1"]}])      # D1 again
    assert any("pin D1 claimed by both 'pwm_out' and 'tach'" in e for e in errs)


def test_unclaimed_module_pins_still_conflict():
    errs = _errors([{"module": "unclaimed", "pins": ["D1"]},
                    {"module": "pwm_out", "pins": ["D1"]}])
    assert any("claimed by both" in e for e in errs)
    # … but get no capability check.
    assert not any("not a valid" in e for e in errs)


def test_family_fallback_when_board_lacks_table():
    # 'bare' board has no tables; family-level pins define adc only.
    errs = _errors([{"module": "scanner", "pins": ["D9"], "dac_pin": "A0",
                     "ack_pins": ["A9"]}], board="bare")
    # adc A9 resolves via the family fallback …
    assert not any("A9" in e for e in errs)
    # … gpio/dac have no table anywhere → explicit table-missing errors.
    assert any("no 'gpio' pin table" in e for e in errs)
    assert any("no 'dac' pin table" in e for e in errs)


@pytest.mark.skipif(bool(_absent(*_FLEET)),
                    reason=f"fleet contracts not present: {_absent(*_FLEET)}")
def test_real_lattice_contracts_pass_pin_validation():
    """The fleet's lattice contracts satisfy the authored board tables."""
    from tools.forge.contract import (load_contract, load_module_manifests,
                                      load_platform)
    for stem in _FLEET:
        target = load_contract(stem, _ROOT)
        platform = load_platform(target, _ROOT)
        manifests = load_module_manifests(target, _ROOT)
        assert validate(target, platform, manifests) == [], stem
