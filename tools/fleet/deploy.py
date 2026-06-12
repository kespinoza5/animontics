"""Deploy command — push fleet desired state to a board.

Negotiation flow:
  1. Load config/nodes/<id>.yaml (desired state) + config/animon.yaml (access)
  2. Try config/boards/<id>.yaml staging copy; else SSH to board for config.yaml
  3. Reconcile: keep existing wiring, add new sensors with METADATA defaults,
     disable sensors removed from nodes/<id>.yaml
  4. Validate result against METADATA constraints
  5. dry_run → print diff and exit
  6. Rsync core/, node/, needed sensor packages; remove unneeded packages
  7. Write new config.yaml to board
  8. pip install deps + restart service
  9. Poll GET / to confirm healthy
 10. Write merged config to config/boards/<id>.yaml staging copy
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

import yaml

from core.config import (
    clear_board_override,
    load_board_override,
    load_board_staging,
    load_fleet,
    load_node_config,
    save_board_override,
    save_board_staging,
)
from core.models import AnimonConfig, AnimonNodeEntry, NodeConfig
from tools.fleet.reconcile import (
    ReconcileError,
    load_all_metadata,
    reconcile,
    validate_connection,
)
from tools.fleet.ssh import SSHError, read_remote_file, rsync_to, run_remote, write_remote_file
from tools.fleet.validate_board import validate_board_tiers


def deploy(
    node_id: str,
    project_root: Path,
    *,
    nodes_dir: Path | None = None,
    animon_path: Path | None = None,
    dry_run: bool = False,
    user_override: str | None = None,
    host_override: str | None = None,
    deploy_path_override: str | None = None,
    config_override: Path | None = None,
    note: str | None = None,
    assume_yes: bool = False,
    is_revert: bool = False,
    verbose: bool = False,
) -> int:
    """Deploy animontics to a node based on desired state in config/nodes/.

    Returns 0 on success, 1 on failure.

    Bootstrap: a board does not need an entry in config/animon.yaml to be
    deployed. Pass host_override (and optionally user_override /
    deploy_path_override) to push to a board reachable at a known address
    before its access details are recorded in animon.yaml. The desired state
    in config/nodes/<id>.yaml is still required.

    Override: pass config_override to push a verbatim, pre-built config.yaml to
    the board for testing / debugging / rollback. It is validated against
    METADATA but NOT reconciled. The staged baseline (config/boards/<id>.yaml)
    is left untouched; instead an override marker (config/boards/<id>.override.yaml)
    is written so the deviation is visible in status/diff and revertible with
    'animon revert <id>'. A plain deploy onto a board with an active override
    prompts before discarding it (unless assume_yes / is_revert).
    """
    def log(msg: str) -> None:
        print(msg)

    def vlog(msg: str) -> None:
        if verbose:
            print(f"  {msg}")

    # ── 1. Load fleet config and locate node ──────────────────────────────────
    try:
        animon = load_fleet(project_root, nodes_dir=nodes_dir, animon_path=animon_path)
    except FileNotFoundError as e:
        print(f"error: {e}")
        return 1

    node = animon.get_node(node_id)
    if node is None:
        ids = [n.id for n in animon.nodes]
        print(f"error: node '{node_id}' not found in config/nodes/")
        print(f"  known nodes: {ids}")
        return 1

    host = host_override or node.reachable_host
    if not host:
        print(
            f"error: node '{node_id}' has no ip or hostname.\n"
            f"  Add access details to config/animon.yaml, or pass --host <ip|hostname>\n"
            f"  to bootstrap a board that is not yet in animon.yaml."
        )
        return 1

    user = user_override or animon.effective_ssh_user(node)
    deploy_path = deploy_path_override or animon.effective_deploy_path(node)
    config_path = f"{deploy_path}/config/config.yaml"  # path on the board

    is_override = config_override is not None
    log(f"Deploying {node_id} → {user}@{host}  (deploy path: {deploy_path})")
    if dry_run:
        log("  [dry-run mode — no changes will be made]")

    metadata = load_all_metadata()
    vlog(f"Loaded metadata for: {sorted(metadata)}")

    # Is there already an ad-hoc override pinned to this board?
    active_override = load_board_override(node_id, project_root)

    if is_override:
        # ── 2a. Override deploy — verbatim, validated, NOT reconciled ──────────
        try:
            raw = Path(config_override).read_text(encoding="utf-8")
            new_config = NodeConfig.model_validate(yaml.safe_load(raw))
        except FileNotFoundError:
            print(f"error: config file not found: {config_override}")
            return 1
        except Exception as e:
            print(f"error: could not parse/validate {config_override}: {e}")
            return 1

        if new_config.node_id != node_id:
            log(f"  warning: config node_id '{new_config.node_id}' does not match "
                f"target node '{node_id}'")

        errors = _validate_against_metadata(new_config, metadata)
        if errors:
            print(f"error: override config failed METADATA validation:")
            for err in errors:
                print(f"  ! {err}")
            return 1

        baseline = load_board_staging(node_id, project_root)
        changes = _describe_override(baseline, new_config)
        log("\nOverride config (verbatim — not reconciled against desired state):")
        for c in changes:
            log(c)
    else:
        # ── 2b. Normal / revert deploy — reconcile against staged baseline ─────
        if active_override and not is_revert:
            log(f"\n⚠ {node_id} has an active OVERRIDE"
                + (f' — note: "{active_override.note}"' if active_override.note else "")
                + f" (deployed {active_override.deployed_at}).")
            log("  A normal deploy reconciles from the staged baseline and discards it.")
            if not dry_run and not _confirm("  Continue and revert the override?", assume_yes):
                log(f"  Aborted. Use 'animon revert {node_id}' to revert explicitly, or "
                    f"'animon deploy {node_id} --config <file>' to apply another override.")
                return 1

        current_config = load_board_staging(node_id, project_root)
        if current_config:
            vlog(f"Using staging copy from config/boards/{node_id}.yaml")
        else:
            vlog(f"No staging copy — reading {config_path} from board via SSH...")
            raw = read_remote_file(host, user, config_path)
            if raw:
                try:
                    current_config = NodeConfig.model_validate(yaml.safe_load(raw))
                except Exception as e:
                    vlog(f"warning: could not parse board config ({e}), treating as fresh install")
            else:
                log("  No existing config.yaml on board — fresh install.")

        try:
            new_config, changes = reconcile(node, current_config, metadata)
        except ReconcileError as e:
            print(f"error: {e}")
            return 1

        # ── Show the diff ──────────────────────────────────────────────────────
        if changes:
            log("\nConfig changes:")
            for c in changes:
                log(c)
        else:
            log("  Config: no changes.")

    # ── 4b. Validate the non-sensor tiers before anything touches the board ───
    # (sensors were validated against METADATA above / during reconcile)
    tier_errors, tier_warnings = validate_board_tiers(new_config)
    if tier_warnings:
        log("\nTier validation warnings:")
        for w in tier_warnings:
            log(f"  ? {w}")
    if tier_errors:
        print("\nerror: board config failed device/effector/policy validation:")
        for err in tier_errors:
            print(f"  ! {err}")
        print("  (fix config/boards/{0}.yaml — or the override file — and retry; "
              "'animon types' lists what this machine knows)".format(node_id))
        return 1

    desired_sensor_types = {ref.type for ref in node.sensors}
    enabled_sensor_types = {s.type for s in new_config.sensors if s.enabled}
    packages_to_deploy = enabled_sensor_types & _available_packages(project_root)
    packages_to_remove = _remote_packages(host, user, deploy_path) - enabled_sensor_types

    if packages_to_deploy:
        log(f"\nPackages to deploy:  {sorted(packages_to_deploy)}")
    if packages_to_remove:
        log(f"Packages to remove:  {sorted(packages_to_remove)}")

    if dry_run:
        log("\n[dry-run] No changes applied.")
        return 0

    # ── 5. Rsync core files ────────────────────────────────────────────────────
    log("\nSyncing files...")
    try:
        _ensure_remote_dir(host, user, deploy_path)

        # core + node + the three non-sensor plugin trees. node/app.py imports
        # devices/effectors/policies unconditionally, so they must ship with it
        # (sensors stay selective — only the packages the node actually runs).
        for subdir in ("core", "node", "devices", "effectors", "policies"):
            log(f"  → {subdir}/")
            rsync_to(project_root / subdir, host, user, f"{deploy_path}/{subdir}/", delete=True)

        log(f"  → sensors/__init__.py")
        rsync_to(project_root / "sensors" / "__init__.py", host, user,
                 f"{deploy_path}/sensors/__init__.py")

        # ── 6. Deploy needed sensor packages ──────────────────────────────────
        for pkg in sorted(packages_to_deploy):
            log(f"  → sensors/{pkg}/")
            rsync_to(project_root / "sensors" / pkg, host, user,
                     f"{deploy_path}/sensors/{pkg}/", delete=True)

        # ── 7. Remove unneeded sensor packages ────────────────────────────────
        for pkg in sorted(packages_to_remove):
            log(f"  ✕ removing sensors/{pkg}/")
            from tools.fleet.ssh import remove_remote_dir
            remove_remote_dir(host, user, f"{deploy_path}/sensors/{pkg}/")

        # ── 8. Write config ───────────────────────────────────────────────────
        log("  → config/config.yaml")
        config_yaml = yaml.dump(
            new_config.model_dump(exclude_none=True),
            default_flow_style=False,
            allow_unicode=True,
        )
        write_remote_file(host, user, config_path, config_yaml)

        # ── 9. Rsync requirements and install deps ────────────────────────────
        log("  → requirements.txt")
        rsync_to(project_root / "requirements.txt", host, user,
                 f"{deploy_path}/requirements.txt")
        run_remote(host, user,
                   f"pip3 install -q -r {deploy_path}/requirements.txt 2>&1 || true")

        # ── 10. Restart service ───────────────────────────────────────────────
        log("  ↺ restarting animontics-node service...")
        run_remote(host, user,
                   "sudo systemctl restart animontics-node 2>/dev/null || "
                   f"echo '(service not installed — start manually)'",
                   check=False)

    except SSHError as e:
        print(f"\nerror: {e}")
        return 1

    # ── 11. Health check ──────────────────────────────────────────────────────
    port = node.port
    url = f"http://{host}:{port}/"
    log(f"\nWaiting for node to come up at {url} ...")
    for attempt in range(10):
        time.sleep(2)
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                info = json.loads(resp.read())
                log(f"  ✓ Node online: {info.get('node_id')} "
                    f"({len(info.get('sensors', []))} sensors)")
                break
        except (urllib.error.URLError, json.JSONDecodeError):
            vlog(f"  attempt {attempt + 1}/10...")
    else:
        log("  ⚠ Node did not respond in time — check service logs on the board.")
        return 1

    # ── 12. Update local state ────────────────────────────────────────────────
    if is_override:
        # Baseline is preserved; record the deviation as an override marker.
        marker_path = save_board_override(
            node_id, new_config, project_root,
            source=str(config_override), note=note,
        )
        vlog(f"Override marker written: {marker_path}")
        log(f"\n⚠ Override active on {node_id}"
            + (f' — note: "{note}"' if note else "")
            + f".\n  Baseline preserved (config/boards/{node_id}.yaml). "
            f"Revert with: animon revert {node_id}")
        return 0

    # Normal / revert deploy: refresh the baseline and clear any override.
    staging_path = save_board_staging(node_id, new_config, project_root)
    vlog(f"Staging copy updated: {staging_path}")
    if clear_board_override(node_id, project_root):
        log(f"  Cleared override marker — {node_id} is back on the staged baseline.")

    log(f"\n{'Revert' if is_revert else 'Deploy'} complete: {node_id}")
    return 0


# ── Helpers ────────────────────────────────────────────────────────────────────

def _available_packages(project_root: Path) -> set[str]:
    """List sensor package directories present in the local repo."""
    sensors_dir = project_root / "sensors"
    return {
        p.name for p in sensors_dir.iterdir()
        if p.is_dir() and (p / "sensor.py").exists()
    }


def _remote_packages(host: str, user: str, deploy_path: str) -> set[str]:
    """List sensor package directories currently on the remote board."""
    stdout, _, rc = run_remote(
        host, user,
        f"ls {deploy_path}/sensors/ 2>/dev/null",
        check=False,
    )
    if rc != 0:
        return set()
    return {p.strip() for p in stdout.split() if p.strip() and p.strip() != "__init__.py"}


def _ensure_remote_dir(host: str, user: str, path: str) -> None:
    subdirs = " ".join(
        f"{path}/{d}" for d in
        ("sensors", "config", "core", "node", "devices", "effectors", "policies")
    )
    run_remote(host, user, f"mkdir -p {subdirs}")


def _validate_against_metadata(config: NodeConfig, metadata: dict[str, dict]) -> list[str]:
    """Validate every enabled sensor in a config against METADATA constraints."""
    errors: list[str] = []
    for s in config.sensors:
        if s.enabled:
            errors.extend(validate_connection(s.type, s.connection, metadata))
    return errors


def _describe_override(baseline: NodeConfig | None, new_config: NodeConfig) -> list[str]:
    """Human-readable diff between the staged baseline and an override config."""
    new_enabled = {s.id: s for s in new_config.sensors if s.enabled}
    base_enabled = {s.id: s for s in baseline.sensors if s.enabled} if baseline else {}

    changes: list[str] = []
    for sid, s in new_enabled.items():
        base = base_enabled.get(sid)
        if base is None:
            changes.append(f"  + {sid} ({s.type}): enabled by override")
        elif base.type != s.type or base.connection != s.connection:
            changes.append(f"  ~ {sid} ({s.type}): differs from baseline wiring")
    for sid, s in base_enabled.items():
        if sid not in new_enabled:
            changes.append(f"  - {sid} ({s.type}): not enabled in override")

    if not changes:
        changes.append("  (override is identical to the staged baseline)")
    return changes


def _confirm(prompt: str, assume_yes: bool) -> bool:
    """Prompt for y/N confirmation. Returns False in non-interactive contexts."""
    import sys
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print(f"{prompt} [y/N] — non-interactive, pass --yes to confirm → no")
        return False
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
