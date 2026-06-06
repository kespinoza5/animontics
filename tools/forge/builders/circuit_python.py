"""CircuitPythonBuilder — composes a generic CircuitPython runtime per instance.

Unlike the AVR target there is no compile step: forge renders one fixed runtime
(mcu/circuit_python/templates/code.py.j2) with the instance's ADS1115 chip list
baked in, into firmware/<id>/code.py, and "deploys" by copying that directory to
the board's CIRCUITPY drive. Firmware families differ only in build (compile vs
none) and deploy (flash vs copy) — everything still stages into firmware/<id>/.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from tools.forge import contract as contract_mod
from tools.forge.builder import Artifact, Builder, BuildContext, BuildError, register_builder

_DEFAULT_BAUD = 115200
_DEFAULT_SAMPLE_HZ = 2


@register_builder("mcu.circuit_python")
class CircuitPythonBuilder(Builder):
    artifact_suffix = ".py"

    def validate(self, ctx: BuildContext) -> list[str]:
        target = ctx.contract
        try:
            platform = contract_mod.load_platform(target, ctx.project_root)
        except contract_mod.ContractError as exc:
            return [str(exc)]
        issues: list[str] = []
        if target.board not in platform.get("boards", {}):
            issues.append(f"board '{target.board}' not in platform.yaml")
        if not any(m.module == "ads1115" for m in target.modules):
            issues.append("circuit_python target has no ads1115 module to read")
        return issues

    def compose(self, ctx: BuildContext) -> Path:
        target = ctx.contract
        root = ctx.project_root
        platform = contract_mod.load_platform(target, root)
        if target.board not in platform.get("boards", {}):
            raise BuildError(f"board '{target.board}' not in platform.yaml")

        # Flatten the ADS1115 chips into an ordered (addr, channel, gain) list.
        addrs: list[int] = []
        channels: list[dict] = []
        sample_hz = _DEFAULT_SAMPLE_HZ
        for mod in target.modules:
            if "sample_hz" in mod.params:
                sample_hz = int(mod.params["sample_hz"])
            if mod.module != "ads1115":
                continue
            for chip in mod.params.get("chips") or []:
                addr = chip["addr"]
                gain = int(chip.get("gain", 1))
                if addr not in addrs:
                    addrs.append(addr)
                for c in chip.get("channels", []):
                    channels.append({"addr": addr, "channel": c, "gain": gain})

        if not channels:
            raise BuildError(f"{target.id}: no ads1115 channels configured")

        src_root = contract_mod.source_root(target, root)
        env = Environment(
            loader=FileSystemLoader(str(src_root / "templates")),
            undefined=StrictUndefined, keep_trailing_newline=True,
        )
        code = env.get_template("code.py.j2").render(
            id=target.id, target=target.target, board=target.board,
            addrs=addrs, channels=channels,
            period=round(1.0 / max(1, sample_hz), 3),
            baud=target.transport.baud or _DEFAULT_BAUD,
        )

        out = ctx.out_dir
        out.mkdir(parents=True, exist_ok=True)
        (out / "code.py").write_text(code, encoding="utf-8")
        return out

    def build(self, ctx: BuildContext) -> Artifact:
        # CircuitPython is interpreted — "build" is just composition.
        project = self.compose(ctx)
        return Artifact(path=project / "code.py", project_dir=project)

    def deploy(self, ctx: BuildContext, artifact: Artifact, *,
               host: str, user: str, dry_run: bool = False) -> None:
        from tools.fleet.ssh import rsync_to

        # Copy the bundle to the board's CIRCUITPY mount (path is board-specific).
        mount = ctx.contract.transport.port or "/media/CIRCUITPY"
        print(f"copying {ctx.contract.id} → {user}@{host}:{mount}")
        rsync_to(artifact.project_dir, host, user, mount, dry_run=dry_run)
