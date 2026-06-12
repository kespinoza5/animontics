"""Board-config validation for the non-sensor tiers — devices, effectors, policies.

Sensors are validated against METADATA during reconcile. The other three tiers
are authored complete in `config/boards/<id>.yaml` (correctly absent from the
desired-state reconcile), which meant a malformed entry — a `sara_r5` device
with no `port`, an effector whose `backend.device` names a nonexistent device,
a policy aimed at a missing effector — only failed at *runtime* on the board.
This pass runs on the dev machine inside `animon deploy`, before anything is
pushed, against each type's `METADATA` — declared module-level in the plugin
package's `__init__.py` (same import-safe pattern as sensors; field reference
in CONTRIBUTING → "Adding a device, effector, or policy").

Errors abort the deploy; warnings (unknown params keys, empty observations)
print but do not block — a SPEC may simply lag a freshly added param.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterator

import yaml

from tools.fleet.reconcile import load_tier_metadata

if TYPE_CHECKING:
    from core.models import NodeConfig


def load_sbc_profile(node_type: str, project_root: Path) -> dict | None:
    """The board model's pin-capability profile, or None if not authored.

    config/profiles/<node_type>.yaml — tracked hardware facts (see its README).
    """
    path = project_root / "config" / "profiles" / f"{node_type}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _gpio_line_specs(config: "NodeConfig") -> Iterator[tuple[str, dict]]:
    """Every libgpiod output-line spec a board config can carry, with its owner."""
    for dc in config.devices:
        for key in ("power_line", "reset_line"):
            spec = dc.params.get(key)
            if isinstance(spec, dict):
                yield f"device '{dc.id}' params.{key}", spec
    for ec in config.effectors:
        if not ec.enabled:
            continue
        spec = (ec.backend or {}).get("line")
        if isinstance(spec, dict):
            yield f"effector '{ec.id}' backend.line", spec
        spec = ec.params.get("sd_line")
        if isinstance(spec, dict):
            yield f"effector '{ec.id}' params.sd_line", spec


def _mcu_command_slots(
    device_id: str, command: str, project_root: Path,
) -> tuple[int | None, str | None]:
    """How many command channels the device's contract provides for `command`.

    Channel index space = the pins of every contract module whose manifest
    `accepts` the command (e.g. set_us → servo_out's pins, in pin order).
    Returns (slots, problem) — slots None when the contract can't be read.
    """
    from tools.forge.contract import ContractError, load_contract, load_module_manifests
    try:
        target = load_contract(device_id, project_root)
        manifests = load_module_manifests(target, project_root)
    except ContractError:
        return None, f"no contract config/mcus/{device_id}.yaml — cannot cross-check channels"
    except Exception as exc:
        return None, f"contract '{device_id}' unreadable ({exc}) — cannot cross-check channels"
    slots = sum(
        len(mod.pins) for mod in target.modules
        if command in (manifests.get(mod.module, {}).get("accepts") or {})
    )
    return slots, None


def validate_board_tiers(
    config: "NodeConfig",
    *,
    device_specs: dict[str, dict] | None = None,
    effector_specs: dict[str, dict] | None = None,
    policy_specs: dict[str, dict] | None = None,
    project_root: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Validate the devices/effectors/policies tiers of a board config.

    Returns (errors, warnings) as human-readable strings. The spec maps
    default to each tier's package METADATA; tests inject their own.
    `project_root` enables the effector→MCU contract cross-check (channel
    indices vs the firmware's command channels); None skips it.
    """
    device_specs = device_specs if device_specs is not None else load_tier_metadata("devices")
    effector_specs = effector_specs if effector_specs is not None else load_tier_metadata("effectors")
    policy_specs = policy_specs if policy_specs is not None else load_tier_metadata("policies")

    errors: list[str] = []
    warnings: list[str] = []

    # ── Duplicate ids within each tier ────────────────────────────────────────
    for tier, entries in (("device", config.devices), ("sensor", config.sensors),
                          ("effector", config.effectors), ("policy", config.policies)):
        seen: set[str] = set()
        for e in entries:
            if e.id in seen:
                errors.append(f"{tier} '{e.id}': duplicate id")
            seen.add(e.id)

    device_ids = {d.id for d in config.devices}
    effector_ids = {e.id for e in config.effectors if e.enabled}

    # ── Devices ───────────────────────────────────────────────────────────────
    for dc in config.devices:
        spec = device_specs.get(dc.kind)
        if spec is None:
            errors.append(
                f"device '{dc.id}': unknown kind '{dc.kind}' "
                f"(known: {sorted(device_specs)})"
            )
            continue
        for field in spec.get("required", []):
            if getattr(dc, field, None) is None:
                errors.append(f"device '{dc.id}' ({dc.kind}): missing required '{field}'")
        known_params = spec.get("params")
        if known_params is not None:
            for key in dc.params:
                if key not in known_params:
                    warnings.append(
                        f"device '{dc.id}' ({dc.kind}): unknown param '{key}' "
                        f"(known: {known_params})"
                    )

    # ── Effectors ─────────────────────────────────────────────────────────────
    for ec in config.effectors:
        if not ec.enabled:
            continue
        spec = effector_specs.get(ec.type)
        if spec is None:
            errors.append(
                f"effector '{ec.id}': unknown type '{ec.type}' "
                f"(known: {sorted(effector_specs)})"
            )
            continue

        backend = ec.backend or {}
        backends = spec.get("backends")
        kind = backend.get("kind", spec.get("default_backend"))
        if backends:
            if kind not in backends:
                errors.append(
                    f"effector '{ec.id}' ({ec.type}): backend kind '{kind}' "
                    f"not supported (supported: {sorted(backends)})"
                )
            else:
                for key in backends[kind]:
                    if backend.get(key) is None:
                        errors.append(
                            f"effector '{ec.id}' ({ec.type}): backend '{kind}' "
                            f"requires '{key}'"
                        )
        # Whatever the spec says, a named backend device must exist on this board.
        dev_ref = backend.get("device")
        if dev_ref is not None and dev_ref not in device_ids:
            errors.append(
                f"effector '{ec.id}' ({ec.type}): backend.device '{dev_ref}' "
                f"is not a declared device (declared: {sorted(device_ids)})"
            )

        # ── Cross-check channel indices against the device's MCU contract ─────
        # (device id = contract stem, the same convention forge resolve uses)
        command = spec.get("mcu_command")
        if (project_root is not None and command and kind == "mcu"
                and dev_ref is not None and dev_ref in device_ids):
            indices = {c.index for c in ec.channels}
            if "channel" in backend:           # e.g. power_rail's single line
                indices.add(int(backend["channel"]))
            if indices:
                slots, problem = _mcu_command_slots(dev_ref, command, project_root)
                if problem:
                    warnings.append(f"effector '{ec.id}' ({ec.type}): {problem}")
                elif slots == 0:
                    errors.append(
                        f"effector '{ec.id}' ({ec.type}): contract '{dev_ref}' has "
                        f"no module accepting '{command}' — firmware can't drive it"
                    )
                else:
                    for idx in sorted(i for i in indices if i >= slots):
                        errors.append(
                            f"effector '{ec.id}' ({ec.type}): channel index {idx} "
                            f"out of range — contract '{dev_ref}' provides "
                            f"{slots} '{command}' channel(s)"
                        )

        known_params = spec.get("params")
        if known_params is not None:
            for key in ec.params:
                if key not in known_params:
                    warnings.append(
                        f"effector '{ec.id}' ({ec.type}): unknown param '{key}' "
                        f"(known: {known_params})"
                    )

    # ── Policies ──────────────────────────────────────────────────────────────
    for pc in config.policies:
        if not pc.enabled:
            continue
        spec = policy_specs.get(pc.type)
        if spec is None:
            errors.append(
                f"policy '{pc.id}': unknown type '{pc.type}' "
                f"(known: {sorted(policy_specs)})"
            )
            continue

        eff_ref = pc.action.get("effector")
        if eff_ref is None:
            if spec.get("needs_effector"):
                errors.append(f"policy '{pc.id}' ({pc.type}): action.effector is required")
        elif eff_ref not in effector_ids:
            errors.append(
                f"policy '{pc.id}' ({pc.type}): action.effector '{eff_ref}' is not "
                f"a declared enabled effector (declared: {sorted(effector_ids)})"
            )

        if spec.get("needs_observation") and not pc.observation:
            warnings.append(f"policy '{pc.id}' ({pc.type}): observation list is empty")

        known_params = spec.get("params")
        if known_params is not None:
            for key in pc.params:
                if key not in known_params:
                    warnings.append(
                        f"policy '{pc.id}' ({pc.type}): unknown param '{key}' "
                        f"(known: {known_params})"
                    )

    # ── SBC pin checks against the node_type's profile ────────────────────────
    # Silicon facts (wrong chip, unknown header line) are errors; activation
    # facts (an overlay must be enabled) are warnings — offline checks can't
    # see live device-tree state. No profile authored → skip entirely.
    profile = (load_sbc_profile(config.node_type, project_root)
               if project_root is not None else None)
    if profile:
        gpio = profile.get("gpio") or {}
        chip = gpio.get("chip")
        known_lines = gpio.get("lines") or {}
        complete = bool(gpio.get("complete", False))
        for owner, spec in _gpio_line_specs(config):
            if spec.get("backend") != "libgpiod":
                continue  # mcu/null backends don't touch SBC pins
            if chip and spec.get("chip") != chip:
                errors.append(
                    f"{owner}: chip '{spec.get('chip')}' — the "
                    f"{config.node_type} profile puts header GPIOs on '{chip}'"
                )
            offset = spec.get("line")
            if offset is not None and known_lines and offset not in known_lines.values():
                msg = (
                    f"{owner}: line {offset} is not a known header GPIO on "
                    f"{config.node_type} (profile lines: {known_lines})"
                )
                (errors if complete else warnings).append(
                    msg if complete else msg + " — partial table, verify with gpioinfo"
                )

        pwm_chips = {int(k): (v or {}) for k, v in
                     ((profile.get("pwm") or {}).get("chips") or {}).items()}
        for ec in config.effectors:
            if not ec.enabled:
                continue
            backend = ec.backend or {}
            if backend.get("kind") != "sbc_pwm":
                continue
            n = int(backend.get("chip", 0))
            if n not in pwm_chips:
                errors.append(
                    f"effector '{ec.id}' ({ec.type}): pwmchip{n} does not exist "
                    f"on {config.node_type} (profile chips: {sorted(pwm_chips)})"
                )
            else:
                overlay = pwm_chips[n].get("overlay")
                if overlay:
                    warnings.append(
                        f"effector '{ec.id}' ({ec.type}): pwmchip{n} requires "
                        f"overlay '{overlay}' — offline check can't confirm it "
                        f"is enabled on the board"
                    )

    # ── Sensors' device references (device-fed array sensors) ────────────────
    for sc in config.sensors:
        if not sc.enabled:
            continue
        for dev_ref in sc.devices:
            if dev_ref not in device_ids:
                errors.append(
                    f"sensor '{sc.id}' ({sc.type}): devices entry '{dev_ref}' is not "
                    f"a declared device (declared: {sorted(device_ids)})"
                )
        for ch in sc.channels:
            if ch.device is not None and ch.device not in device_ids:
                errors.append(
                    f"sensor '{sc.id}' ({sc.type}): channel '{ch.signal}' reads "
                    f"device '{ch.device}', which is not declared"
                )

    return errors, warnings
