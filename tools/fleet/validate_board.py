"""Board-config validation for the non-sensor tiers — devices, effectors, policies.

Sensors are validated against METADATA during reconcile. The other three tiers
are authored complete in `config/boards/<id>.yaml` (correctly absent from the
desired-state reconcile), which meant a malformed entry — a `sara_r5` device
with no `port`, an effector whose `backend.device` names a nonexistent device,
a policy aimed at a missing effector — only failed at *runtime* on the board.
This pass runs on the dev machine inside `animon deploy`, before anything is
pushed, against each type's `SPEC` (see Device.SPEC / EffectorBase.SPEC /
PolicyBase.SPEC).

Errors abort the deploy; warnings (unknown params keys, empty observations)
print but do not block — a SPEC may simply lag a freshly added param.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

# Side-effect imports: populate the three registries so specs are available.
import devices    # noqa: F401
import effectors  # noqa: F401
import policies   # noqa: F401

from core.device import registered_specs as _device_specs
from core.effector_base import registered_specs as _effector_specs
from core.policy import registered_specs as _policy_specs

if TYPE_CHECKING:
    from core.models import NodeConfig


def validate_board_tiers(
    config: "NodeConfig",
    *,
    device_specs: dict[str, dict] | None = None,
    effector_specs: dict[str, dict] | None = None,
    policy_specs: dict[str, dict] | None = None,
) -> tuple[list[str], list[str]]:
    """Validate the devices/effectors/policies tiers of a board config.

    Returns (errors, warnings) as human-readable strings. The spec maps
    default to the live registries; tests inject their own.
    """
    device_specs = device_specs if device_specs is not None else _device_specs()
    effector_specs = effector_specs if effector_specs is not None else _effector_specs()
    policy_specs = policy_specs if policy_specs is not None else _policy_specs()

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
        if backends:
            kind = backend.get("kind", spec.get("default_backend"))
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
