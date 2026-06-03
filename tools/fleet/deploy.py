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

from core.config import load_board_staging, load_fleet, load_node_config, save_board_staging
from core.models import AnimonConfig, AnimonNodeEntry, NodeConfig
from tools.fleet.reconcile import ReconcileError, load_all_metadata, reconcile
from tools.fleet.ssh import SSHError, read_remote_file, rsync_to, run_remote, write_remote_file


def deploy(
    node_id: str,
    project_root: Path,
    *,
    nodes_dir: Path | None = None,
    animon_path: Path | None = None,
    dry_run: bool = False,
    user_override: str | None = None,
    verbose: bool = False,
) -> int:
    """Deploy animontics to a node based on desired state in config/nodes/.

    Returns 0 on success, 1 on failure.
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

    host = node.ip or node.hostname
    if not host:
        print(f"error: node '{node_id}' has no ip or hostname in animon.yaml")
        return 1

    user = user_override or animon.effective_ssh_user(node)
    deploy_path = animon.effective_deploy_path(node)
    config_path = f"{deploy_path}/config/config.yaml"  # path on the board

    log(f"Deploying {node_id} → {user}@{host}  (deploy path: {deploy_path})")
    if dry_run:
        log("  [dry-run mode — no changes will be made]")

    # ── 2. Read current board config (staging copy first, then SSH) ──────────
    current_config: NodeConfig | None = None

    # Try local staging copy first (allows offline dry-run)
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

    # ── 3. Load sensor METADATA and reconcile ─────────────────────────────────
    metadata = load_all_metadata()
    vlog(f"Loaded metadata for: {sorted(metadata)}")

    try:
        new_config, changes = reconcile(node, current_config, metadata)
    except ReconcileError as e:
        print(f"error: {e}")
        return 1

    # ── 4. Show the diff ───────────────────────────────────────────────────────
    if changes:
        log("\nConfig changes:")
        for c in changes:
            log(c)
    else:
        log("  Config: no changes.")

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

        for subdir in ("core", "node"):
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

    # ── 12. Update local staging copy ────────────────────────────────────────
    staging_path = save_board_staging(node_id, new_config, project_root)
    vlog(f"Staging copy updated: {staging_path}")

    log(f"\nDeploy complete: {node_id}")
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
    run_remote(host, user, f"mkdir -p {path}/sensors {path}/config {path}/core {path}/node")
