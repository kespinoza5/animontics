"""Firmware build-state drift — is each MCU's built artifact current with its contract?

Deploy treats node software as desired state; firmware is composed separately
by forge and flashed by hand (it needs the hardware). This module is the seam
between the two: given a node's declared MCUs (`usb_mcus` in the desired
state), report which contracts have never been built or have changed since
their last build. `animon status`/`diff` surface the notes as drift; `animon
deploy` prints them as warnings — it never builds or flashes itself.

The check is offline and mtime-based: config/mcus/<stem>.yaml newer than every
file under firmware/<stem>/ means the build no longer reflects the contract.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import AnimonUsbMcu


def firmware_drift(usb_mcus: "list[AnimonUsbMcu]", project_root: Path) -> list[str]:
    """Human-readable notes for every declared MCU whose firmware lags its contract.

    Empty list = everything declared is built and current. MCU entries with
    neither an id nor a contract stem (placeholders) are skipped.
    """
    notes: list[str] = []
    for mcu in usb_mcus:
        stem = mcu.contract or mcu.id
        if not stem:
            continue

        contract = project_root / "config" / "mcus" / f"{stem}.yaml"
        if not contract.exists():
            notes.append(
                f"firmware: {stem} — declared in desired state but has no "
                f"contract (config/mcus/{stem}.yaml)"
            )
            continue

        fw_dir = project_root / "firmware" / stem
        built = [p for p in fw_dir.rglob("*") if p.is_file()] if fw_dir.exists() else []
        if not built:
            notes.append(f"firmware: {stem} — not built (forge build {stem})")
        elif contract.stat().st_mtime > max(p.stat().st_mtime for p in built):
            notes.append(
                f"firmware: {stem} — stale, contract newer than the last build "
                f"(forge build {stem})"
            )
    return notes
