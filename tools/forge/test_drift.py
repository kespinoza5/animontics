"""Unit tests for firmware build-state drift (contract vs firmware/<id>/)."""
from __future__ import annotations

import os

from core.models import AnimonUsbMcu
from tools.forge.drift import firmware_drift


def _mcu(stem: str) -> AnimonUsbMcu:
    return AnimonUsbMcu(type="rp2040", usb_port="1-1", id=stem)


def _project(tmp_path, *, contract: str | None = None, built: bool = False):
    """Lay out a minimal project tree for one MCU stem."""
    (tmp_path / "config" / "mcus").mkdir(parents=True)
    if contract:
        (tmp_path / "config" / "mcus" / f"{contract}.yaml").write_text(
            "id: x\n", encoding="utf-8")
    if built and contract:
        fw = tmp_path / "firmware" / contract
        fw.mkdir(parents=True)
        (fw / "code.py").write_text("# built\n", encoding="utf-8")
    return tmp_path


def test_built_and_current_is_clean(tmp_path):
    root = _project(tmp_path, contract="lxiao", built=True)
    # Build output newer than the contract (the normal state).
    contract = root / "config" / "mcus" / "lxiao.yaml"
    os.utime(contract, (1_000_000, 1_000_000))
    assert firmware_drift([_mcu("lxiao")], root) == []


def test_missing_contract_is_reported(tmp_path):
    root = _project(tmp_path)
    [note] = firmware_drift([_mcu("ghost")], root)
    assert "no contract" in note and "ghost" in note


def test_never_built_is_reported(tmp_path):
    root = _project(tmp_path, contract="lxiao", built=False)
    [note] = firmware_drift([_mcu("lxiao")], root)
    assert "not built" in note


def test_stale_build_is_reported(tmp_path):
    root = _project(tmp_path, contract="lxiao", built=True)
    artifact = root / "firmware" / "lxiao" / "code.py"
    os.utime(artifact, (1_000_000, 1_000_000))     # build long ago …
    # … contract edited now (default mtime = now) → stale.
    [note] = firmware_drift([_mcu("lxiao")], root)
    assert "stale" in note


def test_contract_stem_overrides_id(tmp_path):
    root = _project(tmp_path, contract="press0", built=True)
    mcu = AnimonUsbMcu(type="samd21", usb_port="1-2", id="anterior", contract="press0")
    contract = root / "config" / "mcus" / "press0.yaml"
    os.utime(contract, (1_000_000, 1_000_000))
    assert firmware_drift([mcu], root) == []


def test_placeholder_without_stem_is_skipped(tmp_path):
    root = _project(tmp_path)
    mcu = AnimonUsbMcu(type="rp2040", usb_port="1-3")    # no id, no contract
    assert firmware_drift([mcu], root) == []
