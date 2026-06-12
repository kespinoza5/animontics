"""contract.py — the forge build contract (config/mcus/<id>.yaml).

This module owns the *shared* contract between build time and run time:

  • build time — which modules to compose, with what params and pins
  • run time   — the channel index→signal map the node-side sensor consumes

The composer owns channel-index assignment: `assign_channels` derives a
deterministic index→source ordering from the modules, preserving any
user-authored `signal`/`calibration`. `validate` does static checks (pin/claim
conflicts, unknown modules, single transport) against the family's platform.yaml
and module manifests. The firmware↔Python boundary is enforced structurally:
nothing here interprets samples — calibration lives only as opaque data the node
applies.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict


class ContractError(Exception):
    """Raised when a contract, platform, or manifest cannot be loaded."""


# ── Models ──────────────────────────────────────────────────────────────────

class McuTransport(BaseModel):
    """How the node reads the MCU's uplink (and, later, sends commands)."""

    type: str = "serial"            # serial (now); spi reserved
    baud: int | None = None
    port: str | None = None         # optional explicit device; else wired/discovered


class McuModule(BaseModel):
    """One source module to compose into the firmware, with its params.

    Module-specific params (sample_hz, freq_hz, …) are kept permissive here and
    validated against the module's own manifest — core models never enumerate
    per-module config, honoring "the module owns its config schema".
    """

    model_config = ConfigDict(extra="allow")

    module: str                     # module type key, e.g. "analog_in"
    pins: list[str] = []

    @property
    def params(self) -> dict[str, Any]:
        return self.model_extra or {}


class McuChannel(BaseModel):
    """One uplink channel: wire index, its source pin/slot, and node-side meaning."""

    index: int                      # position in the protocol frame
    source: str                     # "analog_in.A0"
    signal: str                     # node-side name, e.g. "mq135"
    calibration: dict[str, Any] = {"type": "raw"}


class McuTarget(BaseModel):
    """One MCU build contract — config/mcus/<id>.yaml."""

    id: str
    target: str                     # builder key, e.g. "mcu.arduino"
    board: str                      # board profile in platform.yaml
    transport: McuTransport = McuTransport()
    modules: list[McuModule] = []
    channels: list[McuChannel] = []

    @property
    def category(self) -> str:      # "mcu" | "fpga" | "accel"
        return self.target.split(".", 1)[0]

    @property
    def family(self) -> str:        # "arduino" | "samd21" | "ice40" | …
        return self.target.split(".", 1)[1] if "." in self.target else self.target


# ── Paths ───────────────────────────────────────────────────────────────────

def contract_path(mcu_id: str, project_root: Path) -> Path:
    return project_root / "config" / "mcus" / f"{mcu_id}.yaml"


def source_root(target: McuTarget, project_root: Path) -> Path:
    """The family's source tree, e.g. mcu/arduino/ or fpga/ice40/."""
    return project_root / target.category / target.family


# ── Loaders ─────────────────────────────────────────────────────────────────

def load_contract(mcu_id: str, project_root: Path) -> McuTarget:
    path = contract_path(mcu_id, project_root)
    if not path.exists():
        raise ContractError(f"no MCU contract at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw.setdefault("id", mcu_id)
    return McuTarget.model_validate(raw)


def load_platform(target: McuTarget, project_root: Path) -> dict[str, Any]:
    """Family platform.yaml, with per-board files merged over the inline map.

    `mcu/<family>/boards/<profile>.yaml` (one small file per board profile)
    holds what would bloat platform.yaml: the pin-capability tables, logic
    voltage, and the runtime board name. A board file's keys take precedence
    over the same profile's inline `boards:` entry.
    """
    path = source_root(target, project_root) / "platform.yaml"
    if not path.exists():
        raise ContractError(f"no platform.yaml at {path}")
    platform = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    boards_dir = source_root(target, project_root) / "boards"
    if boards_dir.is_dir():
        boards = platform.setdefault("boards", {})
        for board_file in sorted(boards_dir.glob("*.yaml")):
            data = yaml.safe_load(board_file.read_text(encoding="utf-8")) or {}
            boards[board_file.stem] = {**boards.get(board_file.stem, {}), **data}
    return platform


def load_module_manifests(target: McuTarget, project_root: Path) -> dict[str, dict]:
    """Load every modules/<name>/manifest.yaml under the family source tree."""
    mods_dir = source_root(target, project_root) / "modules"
    manifests: dict[str, dict] = {}
    if not mods_dir.is_dir():
        return manifests
    for manifest in sorted(mods_dir.glob("*/manifest.yaml")):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        manifests[data.get("module") or manifest.parent.name] = data
    return manifests


# ── Channel assignment (composer-owned) ──────────────────────────────────────

def provided_sources(target: McuTarget, manifests: dict[str, dict]) -> list[str]:
    """Ordered channel `source` ids contributed by the contract's modules.

    A module's manifest declares `provides.channels`: "per_pin" (one per
    configured pin) or an integer count. Module order in the contract is the
    wire order, so the assignment is deterministic.
    """
    sources: list[str] = []
    for mod in target.modules:
        provides = (manifests.get(mod.module, {}).get("provides") or {}).get("channels")
        if provides == "per_pin":
            sources += [f"{mod.module}.{pin}" for pin in mod.pins]
        elif provides == "per_chip_channel":          # ADS1115: chips × their channels
            for chip in mod.params.get("chips") or []:
                addr = chip.get("addr")
                addr_s = hex(addr) if isinstance(addr, int) else str(addr)
                sources += [f"{mod.module}.{addr_s}.{c}" for c in chip.get("channels", [])]
        elif isinstance(provides, int):
            sources += [f"{mod.module}.{i}" for i in range(provides)]
    return sources


def assign_channels(target: McuTarget, manifests: dict[str, dict]) -> list[McuChannel]:
    """Derive index→source channels, preserving any user-authored signal/calibration."""
    existing = {c.source: c for c in target.channels}
    channels: list[McuChannel] = []
    for index, source in enumerate(provided_sources(target, manifests)):
        prev = existing.get(source)
        channels.append(McuChannel(
            index=index,
            source=source,
            signal=prev.signal if prev else source,
            calibration=prev.calibration if prev else {"type": "raw"},
        ))
    return channels


# ── Validation ──────────────────────────────────────────────────────────────

def _resolve_pinset(kind: str, board_def: dict, family_pins: dict) -> list | None:
    """Pin list for a capability kind: per-board table first, family fallback.

    `kind` may be flat ("pwm") or role-dotted ("spi.mosi", "i2s.bclk") — bus
    protocols are role-bound (TX≠RX, BCLK≠DIN), so their tables nest one level.
    Returns None when neither table defines the kind.
    """
    for source in (board_def.get("pins") or {}, family_pins):
        node: Any = source
        for part in kind.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        if isinstance(node, list):
            return node
    return None


def _claimed_pins(mod: McuModule, manifest: dict) -> list[tuple[str, str | None]]:
    """(pin, capability-kind) pairs this module claims.

    The manifest's `claims` maps param names to capability kinds —
    `{pins: pwm, dac_pin: dac, ack_pins: adc}`. "pins" is the McuModule.pins
    field; any other param holds one pin name or a list of them. Pins in
    `mod.pins` without a claim still participate (kind None) so the
    one-module-per-pin conflict rule covers them.
    """
    claims: dict[str, str] = manifest.get("claims") or {}
    pairs: list[tuple[str, str | None]] = []
    if mod.pins and "pins" not in claims:
        pairs += [(p, None) for p in mod.pins]
    for param, kind in claims.items():
        value = mod.pins if param == "pins" else mod.params.get(param)
        if not value:
            continue
        for pin in (value if isinstance(value, list) else [value]):
            pairs.append((str(pin), kind))
    return pairs


def validate(target: McuTarget, platform: dict, manifests: dict[str, dict]) -> list[str]:
    """Static checks. Returns human-readable problems (empty == OK)."""
    errors: list[str] = []
    family = target.family

    boards = platform.get("boards", {})
    if target.board not in boards:
        errors.append(f"board '{target.board}' not in platform.yaml ({sorted(boards)})")
    board_def = boards.get(target.board) or {}

    family_pins = platform.get("pins", {})
    claimed: dict[str, str] = {}     # pin -> module that claimed it
    transports: list[str] = []

    for mod in target.modules:
        manifest = manifests.get(mod.module)
        if manifest is None:
            errors.append(f"unknown module '{mod.module}' (no mcu/{family}/modules/{mod.module}/)")
            continue
        if family not in manifest.get("platforms", []):
            errors.append(f"module '{mod.module}' does not support platform '{family}'")
        if manifest.get("role") == "transport":
            transports.append(mod.module)

        for pin, kind in _claimed_pins(mod, manifest):
            if kind is not None:
                valid = _resolve_pinset(kind, board_def, family_pins)
                if valid is None:
                    errors.append(
                        f"module '{mod.module}': no '{kind}' pin table for board "
                        f"'{target.board}' (add it to the board file / platform.yaml)"
                    )
                elif pin not in valid:
                    errors.append(
                        f"module '{mod.module}': {pin} is not a valid {kind} pin "
                        f"on '{target.board}' (valid: {valid})"
                    )
            if pin in claimed:
                who = claimed[pin]
                errors.append(
                    f"pin {pin} claimed twice by '{mod.module}'" if who == mod.module
                    else f"pin {pin} claimed by both '{who}' and '{mod.module}'"
                )
            else:
                claimed[pin] = mod.module

    if len(transports) != 1:
        errors.append(f"exactly one transport module required, found {len(transports)}: {transports}")

    # Channels are hand-authored (so the file stays readable + commented). They
    # must match the order the modules provide — `forge channels` prints the
    # canonical block to paste/check against.
    expected = provided_sources(target, manifests)
    if target.channels:
        authored = [c.source for c in target.channels]
        if len(authored) != len(expected):
            errors.append(
                f"channels: contract lists {len(authored)} but modules provide {len(expected)}"
            )
        elif authored != expected:
            errors.append(
                f"channels: source order does not match module/pin order — "
                f"expected {expected}, got {authored}"
            )
    return errors
