"""animon — fleet management CLI for animontics.

Usage:
    animon deploy <node-id> [--dry-run] [--user USER] [--verbose]
    animon status  [<node-id>] [--json]
    animon diff   <node-id>   [--user USER] [--verbose]
    animon pull   <node-id>   [--user USER] [--dry-run]
    animon probe  <node-id>   [--user USER]
    animon types

Fleet config is read from two sources in the project's config/ directory:
    config/nodes/<id>.yaml    Desired state per node (in repo, no secrets)
    config/animon.yaml        Access layer: IPs, SSH users (gitignored)

Global options:
    --access PATH   Path to animon.yaml access config  (default: config/animon.yaml)
    --nodes PATH    Path to nodes/ desired-state dir   (default: config/nodes/)

Exit codes:
    0  success / all nodes in sync
    1  error   (config problem, connection failure, etc.)
    2  drift   (nodes reachable but board state differs from desired state)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Return the project root (parent of the tools/ directory)."""
    return Path(__file__).resolve().parent.parent.parent


def _default_nodes_dir() -> Path:
    return _project_root() / "config" / "nodes"


def _default_animon_path() -> Path:
    return _project_root() / "config" / "animon.yaml"


def _load_fleet(args: argparse.Namespace):
    """Load fleet config from CLI args, raising SystemExit on failure."""
    from core.config import load_fleet
    try:
        return load_fleet(
            _project_root(),
            nodes_dir=args.nodes,
            animon_path=args.access,
        )
    except FileNotFoundError as e:
        print(f"error: {e}")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

def _cmd_deploy(args: argparse.Namespace) -> int:
    from tools.fleet.deploy import deploy
    return deploy(
        node_id=args.node_id,
        project_root=_project_root(),
        nodes_dir=args.nodes,
        animon_path=args.access,
        dry_run=args.dry_run,
        user_override=args.user,
        host_override=args.host,
        deploy_path_override=args.deploy_path,
        config_override=args.config,
        note=args.note,
        assume_yes=args.yes,
        verbose=args.verbose,
    )


def _cmd_revert(args: argparse.Namespace) -> int:
    from core.config import load_board_override
    from tools.fleet.deploy import deploy

    override = load_board_override(args.node_id, _project_root())
    if override is None:
        print(f"No active override for '{args.node_id}' — nothing to revert.")
        return 0

    print(f"Reverting {args.node_id} to staged baseline"
          + (f' (was: "{override.note}")' if override.note else "")
          + ".")
    return deploy(
        node_id=args.node_id,
        project_root=_project_root(),
        nodes_dir=args.nodes,
        animon_path=args.access,
        dry_run=args.dry_run,
        user_override=args.user,
        host_override=args.host,
        deploy_path_override=args.deploy_path,
        is_revert=True,
        verbose=args.verbose,
    )


def _cmd_status(args: argparse.Namespace) -> int:
    from tools.fleet.sync import status
    return status(
        nodes_dir=args.nodes,
        animon_path=args.access,
        node_id=args.node_id,
        project_root=_project_root(),
        user_override=args.user,
        json_output=args.json,
    )


def _cmd_diff(args: argparse.Namespace) -> int:
    from tools.fleet.sync import diff
    return diff(
        node_id=args.node_id,
        project_root=_project_root(),
        nodes_dir=args.nodes,
        animon_path=args.access,
        user_override=args.user,
        verbose=args.verbose,
    )


def _cmd_pull(args: argparse.Namespace) -> int:
    from tools.fleet.sync import pull
    return pull(
        node_id=args.node_id,
        project_root=_project_root(),
        nodes_dir=args.nodes,
        animon_path=args.access,
        user_override=args.user,
        dry_run=args.dry_run,
    )


def _cmd_types(args: argparse.Namespace) -> int:
    """List every plugin type available on this machine, with its one-liner."""
    from tools.fleet.reconcile import load_tier_metadata

    def section(tier: str) -> None:
        entries = {
            t: m.get("description", m.get("name", ""))
            for t, m in load_tier_metadata(tier).items()
        }
        print(f"\n{tier.capitalize()} ({tier}/ — METADATA)")
        if not entries:
            print("  (none found on this machine)")
        width = max((len(k) for k in entries), default=0)
        for key in sorted(entries):
            print(f"  {key:<{width}}  {entries[key]}")

    for tier in ("sensors", "devices", "effectors", "policies"):
        section(tier)
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    from tools.fleet.probe import (
        format_probe_report,
        match_hardware_to_sensors,
        probe_hardware,
    )
    from tools.fleet.reconcile import load_all_metadata

    animon = _load_fleet(args)
    node = animon.get_node(args.node_id)
    if node is None:
        print(f"error: node '{args.node_id}' not found")
        return 1

    host = node.ip or node.hostname
    user = args.user or animon.effective_ssh_user(node)

    print(f"Probing {args.node_id} ({host}) as {user}...")
    detected = probe_hardware(host, user)
    metadata = load_all_metadata()
    desired_types = [ref.type for ref in node.sensors]
    matches = match_hardware_to_sensors(detected, metadata)

    print(format_probe_report(args.node_id, detected, matches, desired_types))
    return 0


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="animon",
        description="Fleet management CLI for animontics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  success / all nodes in sync
  1  error (config problem, connection failure, etc.)
  2  drift (nodes reachable but config differs from animon.yaml)

Examples:
  animon status
  animon status my_sbc_node --json
  animon diff my_sbc_node
  animon deploy my_sbc_node --dry-run
  animon deploy my_sbc_node --verbose
  animon pull my_pizero_node
  animon probe my_sbc_node
""",
    )

    parser.add_argument(
        "--access",
        metavar="PATH",
        type=Path,
        default=_default_animon_path(),
        help="Path to access config (default: config/animon.yaml)",
    )
    parser.add_argument(
        "--nodes",
        metavar="DIR",
        type=Path,
        default=_default_nodes_dir(),
        help="Path to nodes/ desired-state directory (default: config/nodes/)",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # ── deploy ────────────────────────────────────────────────────────────────
    p_deploy = subparsers.add_parser(
        "deploy",
        help="Push desired state from animon.yaml to a board.",
        description=(
            "Reconciles the node's desired state (config/nodes/<id>.yaml) with the "
            "board's current config and deploys any necessary changes. Syncs code, "
            "updates config, restarts the service, and waits for the node to come back "
            "online. Pass --host to bootstrap a board not yet listed in config/animon.yaml."
        ),
    )
    p_deploy.add_argument("node_id", metavar="NODE-ID", help="Node ID (must exist in config/nodes/)")
    p_deploy.add_argument("--dry-run", action="store_true",
                          help="Show what would change without applying anything")
    p_deploy.add_argument("--user", metavar="USER",
                          help="Override SSH user (default: animon.yaml defaults.ssh_user)")
    p_deploy.add_argument("--host", metavar="IP|HOSTNAME",
                          help="Bootstrap: deploy to this address directly, bypassing "
                               "animon.yaml. Use for a board not yet in the access config.")
    p_deploy.add_argument("--deploy-path", metavar="PATH", dest="deploy_path",
                          help="Override install path on the board "
                               "(default: animon.yaml defaults.deploy_path, /opt/animontics)")
    p_deploy.add_argument("--config", metavar="PATH", type=Path,
                          help="Deploy this config.yaml verbatim (validated, not "
                               "reconciled) as an override for testing/debugging/rollback. "
                               "Baseline is preserved; revert with 'animon revert'.")
    p_deploy.add_argument("--note", metavar="TEXT",
                          help="Reason for an override deploy, recorded in the marker "
                               "and shown by status (use with --config)")
    p_deploy.add_argument("--yes", "-y", action="store_true",
                          help="Skip the confirmation prompt when a normal deploy would "
                               "discard an active override")
    p_deploy.add_argument("--verbose", "-v", action="store_true",
                          help="Show detailed progress")
    p_deploy.set_defaults(func=_cmd_deploy)

    # ── revert ──────────────────────────────────────────────────────────────────
    p_revert = subparsers.add_parser(
        "revert",
        help="Discard a board's active override and restore the staged baseline.",
        description=(
            "Reverts a board that is running an ad-hoc override (deployed with "
            "'deploy --config') back to the staged baseline by reconciling from "
            "config/nodes/ + config/boards/<id>.yaml, then deletes the override marker. "
            "A no-op if the node has no active override."
        ),
    )
    p_revert.add_argument("node_id", metavar="NODE-ID", help="Node ID (must exist in config/nodes/)")
    p_revert.add_argument("--user", metavar="USER", help="Override SSH user")
    p_revert.add_argument("--host", metavar="IP|HOSTNAME",
                          help="Deploy to this address directly, bypassing animon.yaml")
    p_revert.add_argument("--deploy-path", metavar="PATH", dest="deploy_path",
                          help="Override install path on the board")
    p_revert.add_argument("--dry-run", action="store_true",
                          help="Show what reverting would change without applying anything")
    p_revert.add_argument("--verbose", "-v", action="store_true",
                          help="Show detailed progress")
    p_revert.set_defaults(func=_cmd_revert)

    # ── status ────────────────────────────────────────────────────────────────
    p_status = subparsers.add_parser(
        "status",
        help="Compare animon.yaml desired state against live board state.",
        description=(
            "Queries GET /config on each reachable node and compares the live config "
            "against animon.yaml. Reports: in-sync, drifted, or unreachable."
        ),
    )
    p_status.add_argument("node_id", metavar="NODE-ID", nargs="?", default=None,
                          help="Check a specific node only (default: all nodes)")
    p_status.add_argument("--json", action="store_true",
                          help="Output results as JSON")
    p_status.add_argument("--user", metavar="USER", help=argparse.SUPPRESS)
    p_status.set_defaults(func=_cmd_status)

    # ── diff ─────────────────────────────────────────────────────────────────
    p_diff = subparsers.add_parser(
        "diff",
        help="Show what 'deploy' would change for a node.",
        description=(
            "Like 'deploy --dry-run' but reads the board config via HTTP first, "
            "falling back to SSH. No changes are made."
        ),
    )
    p_diff.add_argument("node_id", metavar="NODE-ID", help="Node ID (must exist in config/nodes/)")
    p_diff.add_argument("--user", metavar="USER",
                        help="Override SSH user (for SSH fallback config read)")
    p_diff.add_argument("--verbose", "-v", action="store_true",
                        help="Show additional reconciliation detail")
    p_diff.set_defaults(func=_cmd_diff)

    # ── pull ─────────────────────────────────────────────────────────────────
    p_pull = subparsers.add_parser(
        "pull",
        help="Pull a board's live config into boards/ staging and nodes/ desired state.",
        description=(
            "Fetches the board's live config.yaml and updates two local files: "
            "config/boards/<id>.yaml (full wiring staging copy) and "
            "config/nodes/<id>.yaml (adds any sensor {id,type} pairs not yet listed). "
            "Does not remove sensors from desired state. Useful after manually editing "
            "a board's config.yaml directly."
        ),
    )
    p_pull.add_argument("node_id", metavar="NODE-ID", help="Node ID (must exist in config/nodes/)")
    p_pull.add_argument("--user", metavar="USER",
                        help="Override SSH user")
    p_pull.add_argument("--dry-run", action="store_true",
                        help="Show what would be added without modifying animon.yaml")
    p_pull.set_defaults(func=_cmd_pull)

    # ── types ─────────────────────────────────────────────────────────────────
    p_types = subparsers.add_parser(
        "types",
        help="List available sensor/device/effector/policy types.",
        description=(
            "Lists every plugin type registered on this machine with its "
            "one-line description — the vocabulary available when authoring "
            "config/boards/<id>.yaml and config/nodes/<id>.yaml."
        ),
    )
    p_types.set_defaults(func=_cmd_types)

    # ── probe ─────────────────────────────────────────────────────────────────
    p_probe = subparsers.add_parser(
        "probe",
        help="SSH into a board and detect connected hardware.",
        description=(
            "Scans I2C buses, UART devices, and USB CDC devices on a remote board. "
            "Matches detected hardware against sensor METADATA and reports which "
            "sensor types are likely connected and on which ports/buses."
        ),
    )
    p_probe.add_argument("node_id", metavar="NODE-ID", help="Node ID (must exist in config/nodes/)")
    p_probe.add_argument("--user", metavar="USER",
                         help="Override SSH user")
    p_probe.set_defaults(func=_cmd_probe)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate command."""
    # Ensure Unicode output works on Windows consoles (CP1252 → UTF-8).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
