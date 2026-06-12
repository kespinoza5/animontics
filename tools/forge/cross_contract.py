"""Cross-contract validation — params that must agree ACROSS contracts.

`forge validate` checks one contract against its own modules and board. But a
scanned lattice is a *conversation* between contracts: the conductor
(`matrix_scan`) sweeps rows and broadcasts a DAC code; the followers
(`scan_follower`) decode that code back into a row index. If `rows` or
`max_code` differ between them, every sweep decodes garbage — and on the bench
it looks exactly like a wiring fault. The contract headers used to say
"rows + max_code MUST match (manual sync)"; this module is that check.

Assumption (documented, revisit if a second lattice appears): all scan-module
contracts under config/mcus/ belong to ONE sweep group. A future multi-lattice
fleet would add an explicit group key to the module params.
"""
from __future__ import annotations

from pathlib import Path

from tools.forge import contract as contract_mod

#: module name → role in the sweep handshake
SCAN_MODULES = {"matrix_scan": "conductor", "scan_follower": "follower"}

#: params every participant must agree on
SHARED_SCAN_PARAMS = ("rows", "max_code")


def _scan_entries(project_root: Path) -> list[tuple[str, str, dict]]:
    """(contract_id, role, module params) for every scan module in config/mcus/.

    Contracts that fail to load are skipped — their own `forge validate` run
    reports the load error; this check only cares about the sweep group.
    """
    entries: list[tuple[str, str, dict]] = []
    mcus_dir = project_root / "config" / "mcus"
    if not mcus_dir.exists():
        return entries
    for path in sorted(mcus_dir.glob("*.yaml")):
        if path.stem == "example":
            continue
        try:
            target = contract_mod.load_contract(path.stem, project_root)
        except Exception:
            # Unparseable / invalid sibling: its own `forge validate` reports
            # that; the sweep check just leaves it out of the group.
            continue
        for mod in target.modules:
            role = SCAN_MODULES.get(mod.module)
            if role:
                entries.append((target.id, role, {**mod.params, "pins": mod.pins}))
    return entries


def cross_contract_issues(target: "contract_mod.McuTarget", project_root: Path) -> list[str]:
    """Sweep-group consistency issues, or [] — also [] when `target` is not a
    scan participant (an unrelated MCU never fails on its neighbours)."""
    if not any(mod.module in SCAN_MODULES for mod in target.modules):
        return []

    entries = _scan_entries(project_root)
    issues: list[str] = []

    # ── Shared params must agree across every participant ─────────────────────
    for param in SHARED_SCAN_PARAMS:
        values: dict[object, list[str]] = {}
        for cid, role, params in entries:
            values.setdefault(params.get(param), []).append(f"{cid}({role})")
        if len(values) > 1:
            detail = "; ".join(
                f"{v!r} in {', '.join(ids)}" for v, ids in values.items()
            )
            issues.append(
                f"sweep param '{param}' differs across contracts — {detail}. "
                f"Conductor and followers decode the same DAC broadcast; "
                f"these must match."
            )

    # ── Conductor's ack pins must match the follower count ────────────────────
    conductors = [(cid, p) for cid, role, p in entries if role == "conductor"]
    followers = [cid for cid, role, _ in entries if role == "follower"]
    for cid, params in conductors:
        ack_pins = params.get("ack_pins") or []
        if len(ack_pins) != len(followers):
            issues.append(
                f"{cid}: matrix_scan declares {len(ack_pins)} ack_pins but "
                f"{len(followers)} scan_follower contract(s) exist "
                f"({', '.join(sorted(followers)) or 'none'}) — one ack line per follower."
            )

    return issues
