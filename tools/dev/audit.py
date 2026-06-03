"""
Sensor-plugin conformance audit — a development tool.

Checks every sensor package under sensors/ against the project's plugin
contract (see CONTRIBUTING.md and CLAUDE.md), plus the cross-file wiring that
a new sensor is supposed to touch (config/nodes/, docs, mkdocs nav, routers).

Why this reads source as TEXT/AST instead of importing:
    Several sensors depend on Linux-only libraries (smbus2, fcntl). On a
    Windows dev box those imports fail, so a runtime check would silently see
    only 3 of 5 sensors. Parsing the files statically lets us audit every
    package regardless of which hardware libs are installed.

Severity:
    ERROR  — breaks deploy or routing at runtime (fleet ReconcileError,
             registry KeyError, dead HTTP route). Exit code 1.
    WARN   — contract/style drift that won't crash but should be fixed
             (missing try/except, missing docs page, __all__ omissions).

Usage:
    python -m tools.dev.audit              # audit all sensors
    python -m tools.dev.audit tf_mini      # audit one package
    python -m tools.dev.audit --verbose    # narrate every check
    python -m tools.dev.audit --warn-as-error
"""
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

ERROR = "ERROR"
WARN  = "WARN"

# config/nodes/ may reference types that are not sensor packages (handled by
# dedicated routers / subsystems). Exclude them from the "unknown type" check.
NON_PACKAGE_TYPES = {"camera"}

REQUIRED_METADATA_KEYS    = ("type", "name", "description", "connection")
REQUIRED_CONNECTION_KEYS  = ("supported", "defaults")


# ── Finding model ─────────────────────────────────────────────────────────────


@dataclass
class Finding:
    level:   str   # ERROR | WARN
    scope:   str   # sensor name, "config/nodes", "docs", etc.
    message: str
    hint:    str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, scope: str, message: str, hint: str = "") -> None:
        self.findings.append(Finding(level, scope, message, hint))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARN]


# ── Verbose checker helper ────────────────────────────────────────────────────


class _Checker:
    """Emits [✓] / [✗] lines when verbose=True; otherwise a silent no-op."""

    def __init__(self, verbose: bool) -> None:
        self._verbose = verbose

    def ok(self, label: str) -> None:
        if self._verbose:
            print(f"  [✓] {label}")

    def fail(self, label: str) -> None:
        if self._verbose:
            print(f"  [✗] {label}")

    def section(self, title: str) -> None:
        if self._verbose:
            print(f"\n{title}")


# ── Static parsing helpers ────────────────────────────────────────────────────


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError):
        return None


def _find_assignment(tree: ast.Module, name: str) -> ast.AST | None:
    """Return the value node of a top-level `name = <value>` assignment."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
    return None


def _dict_keys(node: ast.AST | None) -> set[str]:
    if not isinstance(node, ast.Dict):
        return set()
    keys: set[str] = set()
    for k in node.keys:
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            keys.add(k.value)
    return keys


def _dict_get(node: ast.AST | None, key: str) -> ast.AST | None:
    if not isinstance(node, ast.Dict):
        return None
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    return None


def _string_list(node: ast.AST | None) -> list[str] | None:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    out: list[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.append(elt.value)
    return out


def _has_import_try_except(tree: ast.Module, pkg: str) -> bool:
    """True if a top-level try/except ImportError wraps the sensor import."""
    for node in tree.body:
        if not isinstance(node, ast.Try):
            continue
        catches_import = any(
            (isinstance(h.type, ast.Name) and h.type.id in ("ImportError", "Exception"))
            for h in node.handlers
        )
        if not catches_import:
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.ImportFrom) and stmt.module and pkg in stmt.module:
                return True
    return False


def _register_key_and_class(sensor_py: Path) -> tuple[str | None, str | None]:
    """Extract (register_key, class_name) from an @register("...") class."""
    tree = _parse(sensor_py)
    if tree is None:
        return None, None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for deco in node.decorator_list:
            if (
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Name)
                and deco.func.id == "register"
                and deco.args
                and isinstance(deco.args[0], ast.Constant)
            ):
                return deco.args[0].value, node.name
    return None, None


# ── Per-sensor checks ─────────────────────────────────────────────────────────


def audit_sensor(pkg_dir: Path, report: Report, chk: _Checker) -> None:
    name        = pkg_dir.name
    init_path   = pkg_dir / "__init__.py"
    sensor_path = pkg_dir / "sensor.py"

    # ── __init__.py present ──────────────────────────────────────────────────
    if not init_path.exists():
        chk.fail("__init__.py present")
        report.add(ERROR, name, "missing __init__.py",
                   "Every sensor package needs an __init__.py with METADATA.")
        return
    chk.ok("__init__.py present")

    tree = _parse(init_path)
    if tree is None:
        chk.fail("__init__.py parses (no syntax errors)")
        report.add(ERROR, name, "__init__.py does not parse (syntax error)")
        return
    chk.ok("__init__.py parses")

    # ── METADATA dict ────────────────────────────────────────────────────────
    metadata = _find_assignment(tree, "METADATA")
    if metadata is None:
        chk.fail("METADATA dict present")
        report.add(ERROR, name, "no METADATA dict in __init__.py",
                   "Without METADATA, `animon deploy` raises ReconcileError on fresh boards.")
    else:
        chk.ok("METADATA dict present")
        md_keys = _dict_keys(metadata)

        # Required top-level keys
        missing_top = [k for k in REQUIRED_METADATA_KEYS if k not in md_keys]
        if missing_top:
            chk.fail(f"METADATA keys: {', '.join(REQUIRED_METADATA_KEYS)}")
            for key in missing_top:
                report.add(ERROR, name, f"METADATA missing required key '{key}'")
        else:
            chk.ok(f"METADATA keys: {', '.join(REQUIRED_METADATA_KEYS)}")

        # Required connection sub-keys
        conn     = _dict_get(metadata, "connection")
        conn_keys = _dict_keys(conn)
        missing_conn = [k for k in REQUIRED_CONNECTION_KEYS if k not in conn_keys]
        if missing_conn:
            chk.fail(f"METADATA.connection keys: {', '.join(REQUIRED_CONNECTION_KEYS)}")
            for key in missing_conn:
                report.add(ERROR, name,
                            f"METADATA['connection'] missing required key '{key}'")
        else:
            chk.ok(f"METADATA.connection keys: {', '.join(REQUIRED_CONNECTION_KEYS)}")

        # METADATA.type must equal the package dir name
        type_node = _dict_get(metadata, "type")
        md_type   = type_node.value if isinstance(type_node, ast.Constant) else None
        if md_type is not None and md_type != name:
            chk.fail(f"METADATA.type matches package dir (got '{md_type}', want '{name}')")
            report.add(ERROR, name,
                        f"METADATA['type'] = '{md_type}' but package dir is '{name}'",
                        "These must match — the type key is how config.yaml selects the package.")
        elif md_type is not None:
            chk.ok(f"METADATA.type matches package dir ('{name}')")

    # ── try/except ImportError wrapper ──────────────────────────────────────
    if not _has_import_try_except(tree, name):
        chk.fail("try/except ImportError wraps sensor import")
        report.add(WARN, name,
                   "sensor import in __init__.py is not wrapped in try/except ImportError",
                   "CONTRIBUTING.md requires it so the module loads on dev machines "
                   "without hardware libs (smbus2/fcntl/serial).")
    else:
        chk.ok("try/except ImportError wraps sensor import")

    # ── __all__ ──────────────────────────────────────────────────────────────
    all_node  = _find_assignment(tree, "__all__")
    all_names = _string_list(all_node)
    if all_names is None:
        chk.fail("__all__ present")
        report.add(WARN, name, "__init__.py has no __all__ list")
    else:
        chk.ok("__all__ present")
        if "METADATA" not in all_names:
            chk.fail("'METADATA' listed in __all__")
            report.add(WARN, name, "__all__ does not include 'METADATA'")
        else:
            chk.ok("'METADATA' listed in __all__")

    # ── sensor.py and @register ──────────────────────────────────────────────
    if not sensor_path.exists():
        chk.fail("sensor.py present")
        report.add(ERROR, name, "missing sensor.py")
    else:
        chk.ok("sensor.py present")
        reg_key, cls_name = _register_key_and_class(sensor_path)
        if reg_key is None:
            chk.fail("@register(\"...\") decorated class found in sensor.py")
            report.add(ERROR, name, "sensor.py has no @register(\"...\") decorated class",
                        "create() can't instantiate this sensor without a registry entry.")
        else:
            if reg_key != name:
                chk.fail(f"@register key matches package dir (got '{reg_key}', want '{name}')")
                report.add(ERROR, name,
                            f"@register(\"{reg_key}\") does not match package dir '{name}'")
            else:
                chk.ok(f"@register key matches package dir ('{name}')")

            if all_names and cls_name and cls_name not in all_names:
                chk.fail(f"sensor class '{cls_name}' listed in __all__")
                report.add(WARN, name,
                            f"sensor class '{cls_name}' is not listed in __all__")
            elif all_names and cls_name:
                chk.ok(f"sensor class '{cls_name}' listed in __all__")


# ── Cross-file checks ─────────────────────────────────────────────────────────


def audit_animon_yaml(root: Path, known: set[str], report: Report, chk: _Checker) -> None:
    """Check config/nodes/*.yaml for unknown sensor type references."""
    try:
        import yaml
    except ImportError:
        report.add(WARN, "config/nodes", "pyyaml not installed — skipped type cross-check")
        return

    nodes_dir = root / "config" / "nodes"
    if not nodes_dir.exists():
        report.add(WARN, "config/nodes", "config/nodes/ directory not found")
        return

    for node_file in sorted(nodes_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(node_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            chk.fail(f"{node_file.name}: parses as YAML")
            report.add(ERROR, f"config/nodes/{node_file.name}", f"does not parse: {exc}")
            continue

        node_id = data.get("id", node_file.stem)
        sensors = data.get("sensors", []) or []
        if not sensors:
            chk.ok(f"{node_file.name}: parses (no sensors listed)")
            continue

        for sensor in sensors:
            stype = sensor.get("type")
            if not stype or stype in NON_PACKAGE_TYPES:
                continue
            if stype not in known:
                chk.fail(f"{node_file.name} → '{stype}' recognized sensor type")
                report.add(ERROR, f"config/nodes/{node_file.name}",
                            f"node '{node_id}' references sensor type '{stype}' "
                            f"with no package under sensors/")
            else:
                chk.ok(f"{node_file.name} → '{stype}' recognized")


def audit_docs(root: Path, sensors: list[str], report: Report, chk: _Checker) -> None:
    mkdocs   = root / "mkdocs.yml"
    nav_text = mkdocs.read_text(encoding="utf-8") if mkdocs.exists() else ""

    for name in sensors:
        doc = root / "docs" / "sensors" / f"{name}.md"
        if not doc.exists():
            chk.fail(f"{name}: docs/sensors/{name}.md exists")
            report.add(WARN, name, f"no docs page (docs/sensors/{name}.md)")
        else:
            chk.ok(f"{name}: docs/sensors/{name}.md exists")
            if f"sensors/{name}.md" not in nav_text:
                chk.fail(f"{name}: referenced in mkdocs.yml nav")
                report.add(WARN, name,
                            f"docs/sensors/{name}.md not referenced in mkdocs.yml nav")
            else:
                chk.ok(f"{name}: referenced in mkdocs.yml nav")


def audit_routers(root: Path, report: Report, chk: _Checker) -> None:
    routers_dir = root / "node" / "routers"
    if not routers_dir.is_dir():
        return

    # camera/i2c/config are subsystem routers that legitimately don't read the
    # sensor registry, so the app.state requirement doesn't apply to them. The
    # check targets registry-backed routers — the generic sensors.py and every
    # per-sensor router (e.g. ir_xcvr.py, vl53l1x.py) — which must reach sensors
    # via request.app.state and never the old register_sensors() coupling.
    skip = {"__init__.py", "config.py", "camera.py", "i2c.py"}
    for router in sorted(routers_dir.glob("*.py")):
        if router.name in skip:
            continue
        text = router.read_text(encoding="utf-8")
        if "register_sensors" in text:
            chk.fail(f"routers/{router.name}: no register_sensors() pattern")
            report.add(ERROR, f"routers/{router.name}",
                        "uses the old register_sensors() pattern",
                        "Routers must read request.app.state.sensors at request time. "
                        "See CONTRIBUTING.md 'Adding a sensor-specific HTTP route'.")
        elif "request.app.state" not in text and "app.state" not in text:
            chk.fail(f"routers/{router.name}: uses request.app.state")
            report.add(WARN, f"routers/{router.name}",
                        "does not reference request.app.state — verify how it reaches sensors")
        else:
            chk.ok(f"routers/{router.name}: uses request.app.state")


# ── Driver ────────────────────────────────────────────────────────────────────


def discover_sensors(root: Path) -> list[Path]:
    sensors_dir = root / "sensors"
    return sorted(
        p for p in sensors_dir.iterdir()
        if p.is_dir() and (p / "__init__.py").exists() and not p.name.startswith("_")
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def run(only: str | None, verbose: bool = False) -> Report:
    root    = _project_root()
    report  = Report()
    chk     = _Checker(verbose)

    pkg_dirs = discover_sensors(root)
    names    = [p.name for p in pkg_dirs]

    if only:
        pkg_dirs = [p for p in pkg_dirs if p.name == only]
        if not pkg_dirs:
            report.add(ERROR, only, f"no sensor package named '{only}' under sensors/")
            return report

    for pkg in pkg_dirs:
        chk.section(f"Checking {pkg.name}...")
        audit_sensor(pkg, report, chk)

    chk.section("Checking config/nodes/...")
    audit_animon_yaml(root, set(names), report, chk)

    chk.section("Checking docs/...")
    audit_docs(root, [p.name for p in pkg_dirs], report, chk)

    chk.section("Checking routers/...")
    audit_routers(root, report, chk)

    return report


def print_report(report: Report, audited: str) -> None:
    if not report.findings:
        print(f"\n[OK] {audited}: all conformance checks passed.")
        return

    by_scope: dict[str, list[Finding]] = {}
    for f in report.findings:
        by_scope.setdefault(f.scope, []).append(f)

    print()
    for scope in sorted(by_scope):
        print(scope)
        for f in by_scope[scope]:
            tag = "[ERROR]" if f.level == ERROR else "[WARN] "
            print(f"  {tag} {f.message}")
            if f.hint:
                print(f"          -> {f.hint}")

    print(f"\nSummary: {len(report.errors)} error(s), {len(report.warnings)} warning(s).")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="python -m tools.dev.audit",
        description="Audit sensor packages against the plugin contract.",
    )
    parser.add_argument("sensor", nargs="?",
                        help="audit only this package (default: all)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="narrate every check as it runs (passing and failing)")
    parser.add_argument("--warn-as-error", action="store_true",
                        help="exit non-zero if there are warnings too")
    args = parser.parse_args(argv)

    report = run(args.sensor, verbose=args.verbose)
    print_report(report, args.sensor or "all sensors")

    if report.errors:
        return 1
    if args.warn_as_error and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
