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
_DEFAULT_PWM_HZ = 25000
_CMD_LOOP_SLEEP = 0.05          # PWM-only board: poll commands at ~20 Hz


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
        kinds = {m.module for m in target.modules}
        if not ({"ads1115", "pwm_out"} & kinds):
            issues.append("circuit_python target needs an ads1115 (in) or pwm_out (out) module")
        return issues

    def compose(self, ctx: BuildContext) -> Path:
        target = ctx.contract
        root = ctx.project_root
        platform = contract_mod.load_platform(target, root)
        if target.board not in platform.get("boards", {}):
            raise BuildError(f"board '{target.board}' not in platform.yaml")

        addrs: list[int] = []
        channels: list[dict] = []        # ADS1115 (addr, channel, gain) in wire order
        pwm_pins: list[str] = []         # CircuitPython board attr names, in command order
        sample_hz = _DEFAULT_SAMPLE_HZ
        pwm_freq = _DEFAULT_PWM_HZ
        for mod in target.modules:
            if "sample_hz" in mod.params:
                sample_hz = int(mod.params["sample_hz"])
            if mod.module == "ads1115":
                for chip in mod.params.get("chips") or []:
                    addr = chip["addr"]
                    gain = int(chip.get("gain", 1))
                    if addr not in addrs:
                        addrs.append(addr)
                    channels += [{"addr": addr, "channel": c, "gain": gain}
                                 for c in chip.get("channels", [])]
            elif mod.module == "pwm_out":
                pwm_pins += list(mod.pins)
                pwm_freq = int(mod.params.get("freq_hz", _DEFAULT_PWM_HZ))

        if not channels and not pwm_pins:
            raise BuildError(f"{target.id}: no ads1115 channels or pwm_out pins configured")

        period = round(1.0 / max(1, sample_hz), 3)
        src_root = contract_mod.source_root(target, root)
        env = Environment(
            loader=FileSystemLoader(str(src_root / "templates")),
            undefined=StrictUndefined, keep_trailing_newline=True,
        )
        code = env.get_template("code.py.j2").render(
            id=target.id, target=target.target, board=target.board,
            addrs=addrs, channels=channels,
            pwm_pins=pwm_pins, pwm_freq=pwm_freq,
            period=period,
            loop_sleep=period if channels else _CMD_LOOP_SLEEP,
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
