"""forge — build-time composition + flashing CLI for downstream targets.

Usage:
    forge validate <mcu-id>            static-check a contract (no build)
    forge build    <mcu-id>            compose + compile → firmware/<id>/
    forge flash    <mcu-id> [--host]   build (if needed) + flash to the target
    forge clean    <mcu-id>            remove firmware/<id>/

The per-instance contract is read from config/mcus/<mcu-id>.yaml; the family
source tree (mcu/<family>/) supplies the modules and templates. forge dispatches
on the contract's `target` key to the matching Builder.

Exit codes:
    0  success / contract valid
    1  error   (bad contract, validation failure, build/flash failure)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import tools.forge.builders  # noqa: F401  (side-effect: registers builders)
from tools.forge import contract as contract_mod
from tools.forge.builder import BuildContext, BuildError, get_builder


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _firmware_dir(mcu_id: str) -> Path:
    return _project_root() / "firmware" / mcu_id


def _load(mcu_id: str) -> tuple[contract_mod.McuTarget, BuildContext]:
    """Load a contract and assemble its BuildContext, or exit(1) on failure."""
    root = _project_root()
    try:
        target = contract_mod.load_contract(mcu_id, root)
    except contract_mod.ContractError as exc:
        print(f"error: {exc}")
        raise SystemExit(1)
    ctx = BuildContext(contract=target, project_root=root, out_dir=_firmware_dir(mcu_id))
    return target, ctx


# ── Commands ──────────────────────────────────────────────────────────────────

def _cmd_validate(args: argparse.Namespace) -> int:
    target, ctx = _load(args.mcu_id)
    issues = _all_issues(target, ctx)
    if issues:
        print(f"{args.mcu_id}: {len(issues)} issue(s)")
        for msg in issues:
            print(f"  - {msg}")
        return 1
    print(f"{args.mcu_id}: OK ({len(contract_mod.provided_sources(target, _manifests(target, ctx)))} channels)")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    target, ctx = _load(args.mcu_id)
    issues = _all_issues(target, ctx)
    if issues:
        print(f"error: {args.mcu_id} has {len(issues)} validation issue(s); run `forge validate {args.mcu_id}`")
        return 1

    # Composer owns channel assignment: derive indices, persist signal/calibration.
    target.channels = contract_mod.assign_channels(target, _manifests(target, ctx))
    contract_mod.save_contract(target, ctx.project_root)

    builder = get_builder(target.target)
    try:
        artifact = builder.build(ctx)
    except BuildError as exc:
        print(f"error: build failed — {exc}")
        return 1
    print(f"built {args.mcu_id} → {artifact.path.relative_to(ctx.project_root)}")
    return 0


def _cmd_flash(args: argparse.Namespace) -> int:
    target, ctx = _load(args.mcu_id)
    host, user = _resolve_host(args)
    if host is None:
        print(f"error: cannot resolve a host for '{args.mcu_id}'. "
              f"Pass --host/--user, or list it under a node's usb_mcus in config/nodes/.")
        return 1
    builder = get_builder(target.target)
    try:
        artifact = builder.build(ctx)
        builder.deploy(ctx, artifact, host=host, user=user, dry_run=args.dry_run)
    except BuildError as exc:
        print(f"error: {exc}")
        return 1
    return 0


def _cmd_clean(args: argparse.Namespace) -> int:
    out = _firmware_dir(args.mcu_id)
    if out.exists():
        shutil.rmtree(out)
        print(f"removed {out.relative_to(_project_root())}")
    else:
        print(f"{args.mcu_id}: nothing to clean")
    return 0


# ── Helpers ─────────────────────────────────────────────────────────────────

def _manifests(target: contract_mod.McuTarget, ctx: BuildContext) -> dict[str, dict]:
    return contract_mod.load_module_manifests(target, ctx.project_root)


def _all_issues(target: contract_mod.McuTarget, ctx: BuildContext) -> list[str]:
    """Contract-level checks + builder-level checks."""
    try:
        platform = contract_mod.load_platform(target, ctx.project_root)
        manifests = contract_mod.load_module_manifests(target, ctx.project_root)
    except contract_mod.ContractError as exc:
        return [str(exc)]
    issues = contract_mod.validate(target, platform, manifests)
    try:
        issues += get_builder(target.target).validate(ctx)
    except BuildError as exc:
        issues.append(str(exc))
    return issues


def _resolve_host(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Resolve (host, user) for an MCU: explicit flags, else the node hosting it."""
    if args.host:
        return args.host, args.user or "pi"
    from core.config import load_fleet
    try:
        fleet = load_fleet(_project_root(), nodes_dir=args.nodes, animon_path=args.access)
    except FileNotFoundError:
        return None, None
    for node in fleet.nodes:
        for mcu in node.usb_mcus:
            if args.mcu_id in {mcu.id, mcu.contract}:
                return (node.ip or node.hostname), (args.user or fleet.effective_ssh_user(node))
    return None, None


# ── Parser ──────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Build-time firmware composition + flashing for animontics MCUs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    p_val = sub.add_parser("validate", help="Static-check an MCU contract (no build).")
    p_val.add_argument("mcu_id", metavar="MCU-ID")
    p_val.set_defaults(func=_cmd_validate)

    p_build = sub.add_parser("build", help="Compose + compile firmware/<id>/.")
    p_build.add_argument("mcu_id", metavar="MCU-ID")
    p_build.set_defaults(func=_cmd_build)

    p_flash = sub.add_parser("flash", help="Build (if needed) + flash to the target.")
    p_flash.add_argument("mcu_id", metavar="MCU-ID")
    p_flash.add_argument("--host", metavar="IP|HOSTNAME",
                         help="Flash via this host directly (bypass node lookup)")
    p_flash.add_argument("--user", metavar="USER", help="SSH user for the host")
    p_flash.add_argument("--dry-run", action="store_true",
                         help="Show the flash steps without executing them")
    p_flash.add_argument("--access", metavar="PATH", type=Path,
                         default=_project_root() / "config" / "animon.yaml",
                         help="Path to access config (default: config/animon.yaml)")
    p_flash.add_argument("--nodes", metavar="DIR", type=Path,
                         default=_project_root() / "config" / "nodes",
                         help="Path to nodes/ directory (default: config/nodes/)")
    p_flash.set_defaults(func=_cmd_flash)

    p_clean = sub.add_parser("clean", help="Remove firmware/<id>/.")
    p_clean.add_argument("mcu_id", metavar="MCU-ID")
    p_clean.set_defaults(func=_cmd_clean)

    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
