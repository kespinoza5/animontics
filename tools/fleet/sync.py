"""Sync commands — status, diff, and pull.

status:  Compare desired state (config/nodes/) against each board's live state.
diff:    Show what 'deploy' would change for a specific node.
pull:    Read a board's live config; update boards/ staging + nodes/ desired state.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from core.config import load_board_override, load_fleet, save_board_staging
from core.models import AnimonConfig, AnimonNodeEntry, NodeConfig
from tools.fleet.reconcile import load_all_metadata, reconcile
from tools.fleet.ssh import SSHError, read_remote_file


# Exit codes
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DRIFT = 2  # in-sync but with drift detected — useful for scripting


def status(
    nodes_dir: Path,
    animon_path: Path,
    node_id: str | None = None,
    *,
    project_root: Path | None = None,
    user_override: str | None = None,
    json_output: bool = False,
) -> int:
    """Show the sync status of all nodes (or a specific node).

    For each reachable node:
      - Queries GET /config to get the board's live config
      - Compares against config/nodes/ desired state
      - Reports: in-sync / drifted / unreachable

    Returns EXIT_OK if all nodes are in sync, EXIT_DRIFT if any drift,
    EXIT_ERROR on config/connection failure.
    """
    try:
        animon = load_fleet(nodes_dir=nodes_dir, animon_path=animon_path)
    except FileNotFoundError as e:
        print(f"error: {e}")
        return EXIT_ERROR

    nodes = [animon.get_node(node_id)] if node_id else animon.nodes
    nodes = [n for n in nodes if n is not None]

    if not nodes:
        print(f"error: node '{node_id}' not found in {animon_path}")
        return EXIT_ERROR

    root = project_root or nodes_dir.parent.parent
    metadata = load_all_metadata()
    results = []
    any_drift = False

    for node in nodes:
        host = node.ip or node.hostname
        port = node.port
        url = f"http://{host}:{port}/config"

        live_config: NodeConfig | None = None
        reachable = False

        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read())
                live_config = NodeConfig.model_validate(data)
                reachable = True
        except (urllib.error.URLError, Exception):
            pass  # unreachable — status will show as unknown

        override = load_board_override(node.id, root)
        drift = _compute_drift(node, live_config, metadata)
        # An active override is an intentional, tracked deviation — surface it
        # distinctly, but it still means the board is not on the staged baseline.
        any_drift = any_drift or bool(drift) or override is not None

        results.append({
            "node_id": node.id,
            "reachable": reachable,
            "host": host,
            "port": port,
            "drift": drift,
            "override": override.note if override else None,
            "overridden": override is not None,
        })

    if json_output:
        print(json.dumps(results, indent=2))
    else:
        _print_status_table(results)

    return EXIT_DRIFT if any_drift else EXIT_OK


def diff(
    node_id: str,
    project_root: Path,
    nodes_dir: Path,
    animon_path: Path,
    *,
    user_override: str | None = None,
    verbose: bool = False,
) -> int:
    """Show what 'deploy' would change for a node without applying anything."""
    try:
        animon = load_fleet(project_root, nodes_dir=nodes_dir, animon_path=animon_path)
    except FileNotFoundError as e:
        print(f"error: {e}")
        return EXIT_ERROR

    node = animon.get_node(node_id)
    if node is None:
        print(f"error: node '{node_id}' not found")
        return EXIT_ERROR

    host = node.ip or node.hostname
    user = user_override or animon.effective_ssh_user(node)
    deploy_path = animon.effective_deploy_path(node)

    # Try HTTP first, fall back to SSH
    live_config = _fetch_config_http(host, node.port)
    if live_config is None:
        raw = read_remote_file(host, user, f"{deploy_path}/config/config.yaml")
        if raw:
            try:
                live_config = NodeConfig.model_validate(yaml.safe_load(raw))
            except Exception:
                pass

    metadata = load_all_metadata()

    try:
        _, changes = reconcile(node, live_config, metadata)
    except Exception as e:
        print(f"error during reconciliation: {e}")
        return EXIT_ERROR

    print(f"diff {node_id}  ({host}:{node.port})")
    override = load_board_override(node_id, project_root)
    if override is not None:
        print(f"  ⚠ active OVERRIDE"
              + (f' — note: "{override.note}"' if override.note else "")
              + f" (deployed {override.deployed_at}).")
        print(f"    Diff below is vs. the staged baseline; run 'animon revert {node_id}' "
              f"to restore it.")
    if changes:
        for c in changes:
            print(c)
        return EXIT_DRIFT
    else:
        print("  No changes — node is in sync with desired state.")
        return EXIT_OK


def pull(
    node_id: str,
    project_root: Path,
    nodes_dir: Path,
    animon_path: Path,
    *,
    user_override: str | None = None,
    dry_run: bool = False,
) -> int:
    """Pull a board's live config into local staging files.

    Two things are updated:
      config/boards/<id>.yaml — full wiring staging copy (gitignored)
      config/nodes/<id>.yaml  — desired state: any new sensor {id,type} pairs
                                that are enabled on the board but not yet listed

    Does not remove sensors from nodes/<id>.yaml that are absent on the board.
    Shows a diff before writing.
    """
    try:
        animon = load_fleet(project_root, nodes_dir=nodes_dir, animon_path=animon_path)
    except FileNotFoundError as e:
        print(f"error: {e}")
        return EXIT_ERROR

    node = animon.get_node(node_id)
    if node is None:
        print(f"error: node '{node_id}' not found in config/nodes/")
        return EXIT_ERROR

    host = node.ip or node.hostname
    user = user_override or animon.effective_ssh_user(node)
    deploy_path = animon.effective_deploy_path(node)

    # ── Fetch live board config ────────────────────────────────────────────────
    live_config = _fetch_config_http(host, node.port)
    if live_config is None:
        raw = read_remote_file(host, user, f"{deploy_path}/config/config.yaml")
        if not raw:
            print(f"error: could not reach {node_id} via HTTP or SSH")
            return EXIT_ERROR
        try:
            live_config = NodeConfig.model_validate(yaml.safe_load(raw))
        except Exception as e:
            print(f"error: could not parse board config: {e}")
            return EXIT_ERROR

    # ── 1. Update boards/ staging copy (always) ───────────────────────────────
    print(f"pull {node_id}:")
    if not dry_run:
        staging_path = save_board_staging(node_id, live_config, project_root)
        print(f"  ✓ config/boards/{node_id}.yaml updated (full wiring)")
    else:
        print(f"  [dry-run] would update config/boards/{node_id}.yaml")

    # ── 2. Update nodes/ desired state — add any new sensor refs ──────────────
    desired_ids = {ref.id for ref in node.sensors}
    new_sensors = [
        s for s in live_config.sensors
        if s.id not in desired_ids and s.enabled
    ]

    if not new_sensors:
        print(f"  config/nodes/{node_id}.yaml: already covers all board sensors.")
        return EXIT_OK

    print(f"  Adding {len(new_sensors)} sensor(s) to config/nodes/{node_id}.yaml:")
    for s in new_sensors:
        print(f"    + {s.id} ({s.type})")

    if dry_run:
        print("  [dry-run] config/nodes/ not modified.")
        return EXIT_OK

    # Update the node's desired-state YAML in place
    node_file = nodes_dir / f"{node_id}.yaml"
    raw_node = yaml.safe_load(node_file.read_text(encoding="utf-8")) or {}
    existing = raw_node.setdefault("sensors", [])
    for s in new_sensors:
        existing.append({"id": s.id, "type": s.type})
    node_file.write_text(
        yaml.dump(raw_node, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"  ✓ config/nodes/{node_id}.yaml updated")
    return EXIT_OK


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fetch_config_http(host: str, port: int) -> NodeConfig | None:
    """Try to fetch the node's config via GET /config."""
    try:
        url = f"http://{host}:{port}/config"
        with urllib.request.urlopen(url, timeout=3) as resp:
            return NodeConfig.model_validate(json.loads(resp.read()))
    except Exception:
        return None


def _compute_drift(
    desired: AnimonNodeEntry,
    live: NodeConfig | None,
    metadata: dict,
) -> list[str]:
    """Return a list of drift descriptions between desired and live state."""
    if live is None:
        return ["unreachable or no config"]

    drift = []
    desired_ids = {ref.id for ref in desired.sensors}
    live_ids = {s.id for s in live.sensors if s.enabled}

    for ref in desired.sensors:
        if ref.id not in live_ids:
            drift.append(f"missing: {ref.id} ({ref.type}) not enabled on board")
        else:
            live_sensor = next(s for s in live.sensors if s.id == ref.id)
            if live_sensor.type != ref.type:
                drift.append(
                    f"type mismatch: {ref.id} is '{live_sensor.type}' on board, "
                    f"'{ref.type}' in desired state"
                )

    extra = live_ids - desired_ids
    for sid in extra:
        drift.append(f"extra: {sid} is enabled on board but not in desired state")

    return drift


def _print_status_table(results: list[dict]) -> None:
    """Print a formatted status table."""
    print(f"{'NODE':<24}  {'HOST':<18}  {'STATUS':<12}  DRIFT")
    print("─" * 72)
    for r in results:
        if not r["reachable"]:
            status_str = "unreachable"
            drift_str = ""
        elif r.get("overridden"):
            status_str = "OVERRIDE"
            note = r.get("override")
            drift_str = f'"{note}"' if note else "ad-hoc config (revert to restore baseline)"
        elif r["drift"]:
            status_str = "DRIFTED"
            drift_str = r["drift"][0] + (f" (+{len(r['drift'])-1} more)" if len(r["drift"]) > 1 else "")
        else:
            status_str = "in-sync"
            drift_str = ""
        print(f"{r['node_id']:<24}  {r['host']:<18}  {status_str:<12}  {drift_str}")
