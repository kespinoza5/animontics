"""check — the whole offline verification battery in one command.

Runs every check a change should pass before it's trusted, with sectioned
output and a one-screen summary. No hardware, no network: everything here is
the offline half of the project's safety net (the bench half is the
validate_* scripts and `animon probe`).

Usage:
    python -m tools.dev.check                  # everything
    python -m tools.dev.check tests forge      # just these steps
    python -m tools.dev.check --no-docs        # skip the slowest step
    python -m tools.dev.check -v               # full output from each step
    python -m tools.dev.check tests -vv        # + per-test pytest names

Steps:
    imports   app factory + every tier's METADATA loads
    tests     bare pytest from the root (skip reasons always shown)
    audit     tools/dev/audit.py sensor conformance (static)
    forge     `forge validate` every contract in config/mcus/
    boards    full deploy-time validation of every config/boards/<id>.yaml
              (tier METADATA, valid: values, pin profiles, contract
              cross-checks, channel resolution, firmware drift)
    docs      mkdocs build

Verbosity (-v, -vv) widens what prints; it never changes pass/fail. Warnings
and skips print at any level — they're shown so they're seen, not so they
block. Exit code: 0 = all green, 1 = any step failed.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
OK, FAIL, WARN, SKIP = f"{GREEN}✓{RESET}", f"{RED}✗{RESET}", f"{YELLOW}?{RESET}", f"{YELLOW}–{RESET}"


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


def _dump(out: str, indent: str = "  ") -> None:
    for line in out.strip().splitlines():
        print(f"{indent}{DIM}{line}{RESET}")


# ── Steps — each returns (ok, one-line summary). `v` is the verbosity level ───

def step_imports(v: int) -> tuple[bool, str]:
    try:
        from node.app import create_app  # noqa: F401
        from tools.fleet.reconcile import load_tier_metadata
        loaded = {t: sorted(load_tier_metadata(t))
                  for t in ("sensors", "devices", "effectors", "policies")}
    except Exception as exc:
        print(f"  {FAIL} {exc}")
        return False, str(exc)
    line = ", ".join(f"{len(names)} {t}" for t, names in loaded.items())
    print(f"  {OK} app factory imports; METADATA: {line}")
    if v >= 1:
        for t, names in loaded.items():
            print(f"      {DIM}{t}: {', '.join(names)}{RESET}")
    return True, line


def step_tests(v: int) -> tuple[bool, str]:
    # -rs always reports skip reasons; -rA (v>=1) reports every non-pass
    # outcome; -v (v>=2) adds per-test names. Skips are surfaced at any level
    # so "why was that skipped?" is answered inline, not left a mystery.
    flags = ["-q", "-rs"] if v == 0 else (["-rA"] if v == 1 else ["-v", "-rA"])
    rc, out = _run([sys.executable, "-m", "pytest", *flags])
    lines = [l for l in out.strip().splitlines() if l.strip()]
    summary = lines[-1] if lines else "(no output)"
    if rc != 0 or v >= 1:
        _dump(out)
    else:
        # quiet pass: still surface the skip-reason lines pytest's -rs printed
        for l in lines:
            if l.startswith("SKIPPED") or l.startswith("XFAIL"):
                print(f"  {SKIP} {l}")
    print(f"  {OK if rc == 0 else FAIL} {summary}")
    return rc == 0, summary


def step_audit(v: int) -> tuple[bool, str]:
    rc, out = _run([sys.executable, "-m", "tools.dev.audit"])
    lines = [l for l in out.strip().splitlines() if l.strip()]
    summary = lines[-1] if lines else "(no output)"
    if rc != 0 or v >= 1:
        _dump(out)
    print(f"  {OK if rc == 0 else FAIL} {summary}")
    return rc == 0, summary


def step_forge(v: int) -> tuple[bool, str]:
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


def step_boards(v: int) -> tuple[bool, str]:
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
        if v >= 1 or not errors:        # warnings: always at -v, else only on a clean board
            for w in tier_warnings:
                print(f"      {DIM}? {w}{RESET}")
        total_errors += len(errors)
        total_warnings += len(tier_warnings)

    summary = f"{len(boards)} boards: {total_errors} errors, {total_warnings} warnings"
    return total_errors == 0, summary


def step_docs(v: int) -> tuple[bool, str]:
    rc, out = _run([sys.executable, "-m", "mkdocs", "build"])
    if rc != 0:
        print(out)
        return False, "build failed"
    if v >= 1:
        _dump(out)
    # keep real diagnostics; mkdocs prints INFO progress and mkdocs-material
    # an informational banner on every run that would drown them out
    issues = [l for l in out.strip().splitlines()
              if "WARNING" in l or "ERROR" in l]
    if v == 0:
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
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="show each step's full output (-vv adds per-test names)")
    args = parser.parse_args(argv)

    selected = args.steps or list(STEPS)
    if args.no_docs and "docs" in selected:
        selected.remove("docs")

    results: list[tuple[str, bool, str, float]] = []
    for name in selected:
        _section(name)
        t0 = time.monotonic()
        ok, summary = STEPS[name](args.verbose)
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
