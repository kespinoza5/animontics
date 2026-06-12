"""check — the whole offline verification battery in one command.

Runs every check a change should pass before it's trusted, with sectioned
output and a one-screen summary. No hardware, no network: everything here is
the offline half of the project's safety net (the bench half is the
validate_* scripts and `animon probe`).

Usage:
    python -m tools.dev.check                  # everything
    python -m tools.dev.check tests forge      # just these steps
    python -m tools.dev.check --no-docs        # skip the slowest step

Steps:
    imports   app factory + every tier's METADATA loads
    tests     bare pytest from the root
    audit     tools/dev/audit.py sensor conformance (static)
    forge     `forge validate` every contract in config/mcus/
    boards    full deploy-time validation of every config/boards/<id>.yaml
              (tier METADATA, valid: values, pin profiles, contract
              cross-checks, channel resolution, firmware drift)
    docs      mkdocs build

Exit code: 0 = all green, 1 = any step failed. Warnings never fail a step —
they print so they're seen, not so they block.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
OK, FAIL, WARN = f"{GREEN}✓{RESET}", f"{RED}✗{RESET}", f"{YELLOW}?{RESET}"


def _root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _section(title: str) -> None:
    print(f"\n{'─' * 3} {title} {'─' * max(0, 60 - len(title))}")


def _run(cmd: list[str]) -> tuple[int, str]:
    """Run a subprocess from the project root; return (rc, combined output)."""
    proc = subprocess.run(
        cmd, cwd=_root(), capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# ── Steps — each returns (ok, one-line summary) ───────────────────────────────

def step_imports() -> tuple[bool, str]:
    try:
        from node.app import create_app  # noqa: F401
        from tools.fleet.reconcile import load_tier_metadata
        counts = {t: len(load_tier_metadata(t))
                  for t in ("sensors", "devices", "effectors", "policies")}
    except Exception as exc:
        print(f"  {FAIL} {exc}")
        return False, str(exc)
    line = ", ".join(f"{n} {t}" for t, n in counts.items())
    print(f"  {OK} app factory imports; METADATA: {line}")
    return True, line


def step_tests() -> tuple[bool, str]:
    rc, out = _run([sys.executable, "-m", "pytest", "-q"])
    tail = [l for l in out.strip().splitlines() if l.strip()][-1:]
    summary = tail[0] if tail else "(no output)"
    if rc != 0:
        print(out)
        return False, summary
    print(f"  {OK} {summary}")
    return True, summary


def step_audit() -> tuple[bool, str]:
    rc, out = _run([sys.executable, "-m", "tools.dev.audit"])
    last = [l for l in out.strip().splitlines() if l.strip()][-1:]
    summary = last[0] if last else "(no output)"
    if rc != 0:
        print(out)
        return False, summary
    print(f"  {OK} {summary}")
    return True, summary


def step_forge() -> tuple[bool, str]:
    mcus = sorted(p.stem for p in (_root() / "config" / "mcus").glob("*.yaml")
                  if p.stem != "example")
    if not mcus:
        print(f"  {WARN} no contracts in config/mcus/ — nothing to validate")
        return True, "no contracts"
    failures = 0
    for mcu in mcus:
        rc, out = _run([sys.executable, "-m", "tools.forge.forge", "validate", mcu])
        if rc == 0:
            print(f"  {OK} {out.strip()}")
        else:
            failures += 1
            for line in out.strip().splitlines():
                print(f"  {FAIL} {line}")
    summary = f"{len(mcus) - failures}/{len(mcus)} contracts OK"
    return failures == 0, summary


def step_boards() -> tuple[bool, str]:
    from core.config import load_node_config
    from tools.fleet.reconcile import load_all_metadata, validate_connection
    from tools.fleet.validate_board import validate_board_tiers
    from tools.forge.resolve import resolve_node_config

    root = _root()
    boards = sorted(
        p for p in (root / "config" / "boards").glob("*.yaml")
        if p.stem != "example" and not p.name.endswith(".override.yaml")
    )
    if not boards:
        print(f"  {WARN} no board configs in config/boards/ — nothing to validate")
        return True, "no boards"

    metadata = load_all_metadata()
    total_errors = total_warnings = 0
    for path in boards:
        try:
            config = load_node_config(path)
        except Exception as exc:
            print(f"  {FAIL} {path.name}: unparseable — {exc}")
            total_errors += 1
            continue

        errors: list[str] = []
        for sc in config.sensors:
            if sc.enabled:
                errors += validate_connection(sc.type, sc.connection, metadata)
        try:
            notes = resolve_node_config(config.model_copy(deep=True), root)
            errors += [n.strip() for n in notes if "⚠" in n]
        except Exception as exc:
            errors.append(f"channel resolution: {exc}")
        tier_errors, tier_warnings = validate_board_tiers(config, project_root=root)
        errors += tier_errors

        mark = OK if not errors else FAIL
        print(f"  {mark} {path.name}: {len(errors)} error(s), "
              f"{len(tier_warnings)} warning(s)")
        for e in errors:
            print(f"      {RED}!{RESET} {e}")
        for w in tier_warnings:
            print(f"      {DIM}? {w}{RESET}")
        total_errors += len(errors)
        total_warnings += len(tier_warnings)

    summary = f"{len(boards)} boards: {total_errors} errors, {total_warnings} warnings"
    return total_errors == 0, summary


def step_docs() -> tuple[bool, str]:
    rc, out = _run([sys.executable, "-m", "mkdocs", "build"])
    # keep real diagnostics; mkdocs prints INFO progress and mkdocs-material
    # an informational banner on every run that would drown them out
    issues = [l for l in out.strip().splitlines()
              if "WARNING" in l or "ERROR" in l]
    if rc != 0:
        print(out)
        return False, "build failed"
    for line in issues:
        print(f"  {DIM}? {line}{RESET}")
    print(f"  {OK} docs build clean" if not issues
          else f"  {OK} docs build ({len(issues)} warning(s))")
    return True, "clean" if not issues else f"{len(issues)} warning(s)"


STEPS = {
    "imports": step_imports,
    "tests": step_tests,
    "audit": step_audit,
    "forge": step_forge,
    "boards": step_boards,
    "docs": step_docs,
}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="check", description="Run the offline verification battery.")
    parser.add_argument("steps", nargs="*", choices=[*STEPS, []],
                        help=f"steps to run (default: all — {', '.join(STEPS)})")
    parser.add_argument("--no-docs", action="store_true",
                        help="skip the mkdocs build (the slowest step)")
    args = parser.parse_args(argv)

    selected = args.steps or list(STEPS)
    if args.no_docs and "docs" in selected:
        selected.remove("docs")

    results: list[tuple[str, bool, str, float]] = []
    for name in selected:
        _section(name)
        t0 = time.monotonic()
        ok, summary = STEPS[name]()
        results.append((name, ok, summary, time.monotonic() - t0))

    _section("summary")
    width = max(len(n) for n, *_ in results)
    for name, ok, summary, dt in results:
        print(f"  {OK if ok else FAIL} {name:<{width}}  {summary}  {DIM}({dt:.1f}s){RESET}")
    failed = [n for n, ok, *_ in results if not ok]
    if failed:
        print(f"\n{RED}FAILED:{RESET} {', '.join(failed)}")
        return 1
    print(f"\n{GREEN}All checks passed.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
