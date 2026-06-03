"""animon — fleet management CLI for animontics.

Usage:
    animon deploy <node-id> [--dry-run] [--user USER] [--verbose]
    animon status  [<node-id>] [--json]
    animon diff   <node-id>   [--user USER] [--verbose]
    animon pull   <node-id>   [--user USER] [--dry-run]
    animon probe  <node-id>   [--user USER]

Fleet config is read from two sources in the project's config/ directory:
    config/nodes/<id>.yaml    Desired state per node (in repo, no secrets)
    config/animon.yaml        Access layer: IPs, SSH users (gitignored)

Global options:
    --access PATH   Path to animon.yaml access config  (default: config/animon.yaml)
    --nodes PATH    Path to nodes/ desired-state dir   (default: config/nodes/)

Exit codes:
    0  success / all nodes in sync
    1  error   (config problem, connection failure, etc.)
    2  drift   (nodes reachable but desired state differs from board reality)
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
        verbose=args.verbose,
    )


def _cmd_status(args: argparse.Namespace) -> int:
    from tools.fleet.sync import status
    return status(
        nodes_dir=args.nodes,
        animon_path=args.access,
        node_id=args.node_id,
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
            "Reconciles animon.yaml desired state with the board's current config "
            "and deploys any necessary changes. Syncs code, updates config, restarts "
            "the service, and waits for the node to come back online."
        ),
    )
    p_deploy.add_argument("node_id", metavar="NODE-ID", help="Node ID from animon.yaml")
    p_deploy.add_argument("--dry-run", action="store_true",
                          help="Show what would change without applying anything")
    p_deploy.add_argument("--user", metavar="USER",
                          help="Override SSH user (default: animon.yaml defaults.ssh_user)")
    p_deploy.add_argument("--verbose", "-v", action="store_true",
                          help="Show detailed progress")
    p_deploy.set_defaults(func=_cmd_deploy)

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
    p_diff.add_argument("node_id", metavar="NODE-ID", help="Node ID from animon.yaml")
    p_diff.add_argument("--user", metavar="USER",
                        help="Override SSH user (for SSH fallback config read)")
    p_diff.add_argument("--verbose", "-v", action="store_true",
                        help="Show additional reconciliation detail")
    p_diff.set_defaults(func=_cmd_diff)

    # ── pull ─────────────────────────────────────────────────────────────────
    p_pull = subparsers.add_parser(
        "pull",
        help="Pull a board's current sensor config into animon.yaml.",
        description=(
            "Reads the board's live sensor config and adds any sensors not already "
            "in animon.yaml. Does not remove sensors from animon.yaml. Useful after "
            "manually editing a board's config.yaml directly."
        ),
    )
    p_pull.add_argument("node_id", metavar="NODE-ID", help="Node ID from animon.yaml")
    p_pull.add_argument("--user", metavar="USER",
                        help="Override SSH user")
    p_pull.add_argument("--dry-run", action="store_true",
                        help="Show what would be added without modifying animon.yaml")
    p_pull.set_defaults(func=_cmd_pull)

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
    p_probe.add_argument("node_id", metavar="NODE-ID", help="Node ID from animon.yaml")
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
