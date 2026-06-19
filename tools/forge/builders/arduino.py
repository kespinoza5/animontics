"""ArduinoBuilder — composes + compiles AVR/Arduino firmware from a contract.

Composition is mechanical: each contract module contributes small jinja
fragments (decl/setup/read/send/loop) that are bucketed and dropped into a fixed
main.ino skeleton, producing direct, concrete calls — no runtime registry, no
vtables, only the modules an instance uses. The hand-written, audited code lives
in the module .h/.cpp libraries under mcu/arduino/modules/.

Compilation shells out to `arduino-cli`. If it is not on PATH, the builder falls
back to running it inside WSL (this project's dev machines keep the AVR toolchain
there) with automatic path translation. Flashing reuses tools/fleet/ssh.py.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from tools.forge import contract as contract_mod
from tools.forge.builder import Artifact, Builder, BuildContext, BuildError, register_builder

# fragment filename → main.ino bucket, with the indentation that bucket needs.
_FRAGMENTS = {
    "decl.j2": "declarations",
    "setup.j2": "setups",
    "read.j2": "sample_reads",
    "send.j2": "transport_send",
    "loop.j2": "loops",
    "poll.j2": "loops",         # transport: drain inbound commands each loop
    "cmd.j2": "commands",       # actuator: a case in the generated onCommand()
}
_INDENT = {
    "declarations": "",
    "setups": "  ",
    "sample_reads": "    ",
    "transport_send": "    ",
    "loops": "  ",
    "commands": "  ",
}
_DEFAULT_BAUD = 115200
_DEFAULT_SAMPLE_HZ = 2


def _pin(token: str) -> str:
    """Translate a contract pin token to an Arduino C++ constant (D13→13, A0→A0)."""
    t = token.strip()
    if len(t) > 1 and t[0] in "Dd" and t[1:].isdigit():
        return t[1:]
    return t


@register_builder("mcu.arduino")
class ArduinoBuilder(Builder):
    artifact_suffix = ".hex"

    # ── validate ──────────────────────────────────────────────────────────────

    def validate(self, ctx: BuildContext) -> list[str]:
        target = ctx.contract
        issues: list[str] = []
        try:
            platform = contract_mod.load_platform(target, ctx.project_root)
            manifests = contract_mod.load_module_manifests(target, ctx.project_root)
        except contract_mod.ContractError as exc:
            return [str(exc)]
        if not platform.get("boards", {}).get(target.board, {}).get("fqbn"):
            issues.append(f"board '{target.board}' has no fqbn in platform.yaml")
        src_root = contract_mod.source_root(target, ctx.project_root)
        for mod in target.modules:
            manifest = manifests.get(mod.module)
            if manifest is None:
                continue  # contract.validate already reports unknown modules
            for src in manifest.get("sources", []):
                if not (src_root / "modules" / mod.module / src).exists():
                    issues.append(f"module '{mod.module}': missing source file {src}")
        return issues

    # ── compose ───────────────────────────────────────────────────────────────

    def compose(self, ctx: BuildContext) -> Path:
        target = ctx.contract
        root = ctx.project_root
        platform = contract_mod.load_platform(target, root)
        manifests = contract_mod.load_module_manifests(target, root)

        fqbn = platform.get("boards", {}).get(target.board, {}).get("fqbn")
        if not fqbn:
            raise BuildError(f"board '{target.board}' has no fqbn in platform.yaml")
        baud = target.transport.baud or _DEFAULT_BAUD

        src_root = contract_mod.source_root(target, root)
        env = Environment(
            loader=FileSystemLoader(str(src_root / "modules")),
            undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True,
        )

        buckets: dict[str, list[str]] = {b: [] for b in set(_FRAGMENTS.values())}
        includes: list[str] = []
        sources: set[tuple[str, str]] = set()
        channel_count = len(contract_mod.provided_sources(target, manifests))
        offset = 0          # running sensor-channel offset (frame slot)
        cmd_offsets: dict[str, int] = {}   # per-command-type running channel offset
        type_counts: dict[str, int] = {}
        sample_hz: list[int] = []

        for mod in target.modules:
            manifest = manifests[mod.module]
            n = type_counts.get(mod.module, 0)
            type_counts[mod.module] = n + 1
            inst = f"{mod.module}{n}"
            params = {**(manifest.get("config") or {}), **mod.params}

            provides = (manifest.get("provides") or {}).get("channels")
            if provides == "per_pin":
                count = len(mod.pins)
            elif isinstance(provides, int):
                count = provides
            else:
                count = 0
            if manifest.get("role") == "sensor" and "sample_hz" in params:
                sample_hz.append(int(params["sample_hz"]))

            # Command channels are indexed PER command type (e.g. set_duty for
            # fans, set_gpio for a relay) — matching the node-side convention the
            # board validator enforces. A module's cmd_offset is the running count
            # of pins from prior modules accepting the SAME command.
            accepts = manifest.get("accepts") or {}
            this_cmd = next(iter(accepts), None)
            cmd_offset = cmd_offsets.get(this_cmd, 0) if this_cmd else 0

            fctx = {
                "inst": inst,
                "pins": [_pin(p) for p in mod.pins],
                "params": params,
                "offset": offset,
                "count": count,
                "npins": len(mod.pins),
                "cmd_offset": cmd_offset,
                "channel_count": channel_count,
                "baud": baud,
                "board": target.board,
                "fqbn": fqbn,
            }
            offset += count
            if this_cmd:
                cmd_offsets[this_cmd] = cmd_offset + len(mod.pins)

            mod_dir = src_root / "modules" / mod.module
            for frag_file, bucket in _FRAGMENTS.items():
                if (mod_dir / frag_file).exists():
                    buckets[bucket].append(
                        env.get_template(f"{mod.module}/{frag_file}").render(**fctx)
                    )
            for src in manifest.get("sources", []):
                sources.add((mod.module, src))
                if src.endswith(".h") and src not in includes:
                    includes.append(src)

        hz = max(sample_hz) if sample_hz else _DEFAULT_SAMPLE_HZ
        sample_period_ms = max(1, round(1000 / hz))

        def block(bucket: str) -> str:
            indent = _INDENT[bucket]
            lines: list[str] = []
            for fragment in buckets[bucket]:
                lines += [indent + ln if ln else ln for ln in fragment.splitlines()]
            return "\n".join(lines)

        main_env = Environment(
            loader=FileSystemLoader(str(src_root / "templates")),
            undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        main = main_env.get_template("main.ino.j2").render(
            id=target.id, target=target.target, board=target.board,
            includes="\n".join(f'#include "{h}"' for h in includes),
            channel_count=channel_count,
            frame_len=channel_count if channel_count > 0 else 1,
            sample_period_ms=sample_period_ms,
            declarations=block("declarations"),
            setups=block("setups"),
            sample_reads=block("sample_reads"),
            transport_send=block("transport_send"),
            loops=block("loops"),
            commands=block("commands"),
        )

        sketch = ctx.out_dir
        if sketch.exists():
            shutil.rmtree(sketch)
        sketch.mkdir(parents=True)
        (sketch / f"{target.id}.ino").write_text(main, encoding="utf-8")
        for mod_type, fname in sorted(sources):
            shutil.copyfile(src_root / "modules" / mod_type / fname, sketch / fname)
        return sketch

    # ── build ─────────────────────────────────────────────────────────────────

    def build(self, ctx: BuildContext) -> Artifact:
        sketch = self.compose(ctx)
        platform = contract_mod.load_platform(ctx.contract, ctx.project_root)
        fqbn = platform["boards"][ctx.contract.board]["fqbn"]
        hex_path = _compile(sketch, fqbn)
        return Artifact(path=hex_path, project_dir=sketch)

    # ── deploy (written; not exercised without hardware) ──────────────────────

    def deploy(self, ctx: BuildContext, artifact: Artifact, *,
               host: str, user: str, dry_run: bool = False) -> None:
        from tools.fleet.ssh import run_remote, rsync_to

        target = ctx.contract
        port = target.transport.port or "/dev/ttyUSB0"
        remote = f"/tmp/forge/{target.id}.hex"
        print(f"flashing {target.id} → {user}@{host} (port {port})")
        run_remote(host, user, "mkdir -p /tmp/forge", dry_run=dry_run)
        rsync_to(artifact.path, host, user, remote, dry_run=dry_run)
        # AVR upload over the USB bootloader. Programmer/baud are Nano defaults;
        # see docs/forge.md for board-specific overrides.
        run_remote(
            host, user,
            f"avrdude -c arduino -p atmega328p -P {port} -b 115200 -U flash:w:{remote}:i",
            dry_run=dry_run,
        )


# ── toolchain invocation (native arduino-cli, else WSL) ───────────────────────

def _compile(sketch: Path, fqbn: str) -> Path:
    out_dir = sketch / "build"
    native = shutil.which("arduino-cli")
    if native:
        _run([native, "compile", "--fqbn", fqbn,
              "--output-dir", str(out_dir), str(sketch)])
    else:
        wsl = shutil.which("wsl") or shutil.which("wsl.exe")
        if not wsl:
            raise BuildError(
                "arduino-cli not found (native or WSL). Install it — see docs/forge.md."
            )
        w_sketch = _to_wsl_path(sketch)
        w_out = _to_wsl_path(out_dir)
        inner = (
            'export PATH="$HOME/.local/bin:$PATH"; '
            f'arduino-cli compile --fqbn {fqbn} '
            f'--output-dir "{w_out}" "{w_sketch}"'
        )
        _run([wsl, "bash", "-lc", inner])

    primary = out_dir / f"{sketch.name}.ino.hex"
    if primary.exists():
        return primary
    hexes = [h for h in out_dir.glob("*.hex") if "with_bootloader" not in h.name]
    if hexes:
        return hexes[0]
    raise BuildError(f"compile produced no .hex in {out_dir}")


def _to_wsl_path(path: Path) -> str:
    """Convert a Windows drive path to its /mnt/<drive> WSL equivalent.

    Done in Python rather than via `wsl wslpath` — passing backslashes through
    wsl.exe as an argument silently strips them.
    """
    s = str(path.resolve())
    if len(s) > 2 and s[1] == ":":
        return f"/mnt/{s[0].lower()}{s[2:].replace(chr(92), '/')}"
    return s.replace(chr(92), "/")


def _run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise BuildError(
            "compile failed:\n" + (res.stdout or "").strip()
            + "\n" + (res.stderr or "").strip()
        )
