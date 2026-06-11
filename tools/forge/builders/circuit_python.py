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
_DEFAULT_SERVO_HZ = 50
_CMD_LOOP_SLEEP = 0.05          # PWM-only board: poll commands at ~20 Hz
_FOLLOWER_LOOP_SLEEP = 0.005    # follower pacing comes from awaiting the conductor

_SENSOR_MODULES = {"ads1115", "tach", "analog_in", "matrix_scan", "scan_follower"}
_ACTUATOR_MODULES = {"pwm_out", "servo_out", "gpio_out"}


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
        kinds = [m.module for m in target.modules]
        if not ((_SENSOR_MODULES | _ACTUATOR_MODULES) & set(kinds)):
            issues.append("circuit_python target needs at least one sensor or actuator module")

        # Scan-sync sanity: a board is conductor OR follower, never both, at most once.
        n_scan = kinds.count("matrix_scan")
        n_follow = kinds.count("scan_follower")
        if n_scan > 1 or n_follow > 1:
            issues.append("at most one matrix_scan / scan_follower module per contract")
        if n_scan and n_follow:
            issues.append("matrix_scan (conductor) and scan_follower are mutually exclusive")
        for mod in target.modules:
            if mod.module == "matrix_scan":
                if not mod.params.get("dac_pin") or not mod.params.get("ack_pins"):
                    issues.append("matrix_scan needs params dac_pin and ack_pins")
                n_inh = len(mod.pins) - 3
                if n_inh < 1:
                    issues.append("matrix_scan pins = 3 select lines + >=1 inhibit line")
                elif int(mod.params.get("rows", 16)) > 8 * n_inh:
                    issues.append(f"matrix_scan rows > 8 x {n_inh} inhibit pin(s)")
            elif mod.module == "scan_follower":
                if not mod.params.get("watch_pin") or not mod.params.get("ack_pin"):
                    issues.append("scan_follower needs params watch_pin and ack_pin")
            elif mod.module in ("servo_out", "analog_in", "gpio_out") and not mod.pins:
                issues.append(f"{mod.module} needs at least one pin")
        return issues

    def compose(self, ctx: BuildContext) -> Path:
        target = ctx.contract
        root = ctx.project_root
        platform = contract_mod.load_platform(target, root)
        if target.board not in platform.get("boards", {}):
            raise BuildError(f"board '{target.board}' not in platform.yaml")

        # Afferent frame sources, kind-tagged, in contract-module order (matches
        # contract.provided_sources, so node channel indices align):
        #   (0, addr, channel, gain) = ADS1115   (1, counter_index, 0, 0) = tach RPM
        #   (2, analog_index, 0, 0)  = native ADC   (3, 0, 0, 0) = scan row tag
        addrs: list[int] = []
        tach_pins: list[str] = []        # CircuitPython board attr names (FG inputs)
        analog_pins: list[str] = []      # native analogio.AnalogIn pins
        frame_sources: list[tuple] = []
        pwm_pins: list[str] = []         # in command order
        servo_pins: list[str] = []       # set_us command order
        gpio_pins: list[str] = []        # set_gpio command order
        scan: dict | None = None         # matrix_scan (conductor) render context
        follower: dict | None = None     # scan_follower render context
        sample_hz = _DEFAULT_SAMPLE_HZ
        pwm_freq = _DEFAULT_PWM_HZ
        servo_freq = _DEFAULT_SERVO_HZ
        servo_min_us, servo_max_us = 500, 2500
        gpio_initial = 0
        ppr = 2
        for mod in target.modules:
            if "sample_hz" in mod.params:
                sample_hz = int(mod.params["sample_hz"])
            if mod.module == "ads1115":
                for chip in mod.params.get("chips") or []:
                    addr = chip["addr"]
                    gain = int(chip.get("gain", 1))
                    if addr not in addrs:
                        addrs.append(addr)
                    frame_sources += [(0, addr, c, gain) for c in chip.get("channels", [])]
            elif mod.module == "tach":
                ppr = int(mod.params.get("pulses_per_rev", 2))
                for pin in mod.pins:
                    frame_sources.append((1, len(tach_pins), 0, 0))
                    tach_pins.append(pin)
            elif mod.module == "analog_in":
                for pin in mod.pins:
                    frame_sources.append((2, len(analog_pins), 0, 0))
                    analog_pins.append(pin)
            elif mod.module == "pwm_out":
                pwm_pins += list(mod.pins)
                pwm_freq = int(mod.params.get("freq_hz", _DEFAULT_PWM_HZ))
            elif mod.module == "servo_out":
                servo_pins += list(mod.pins)
                servo_freq = int(mod.params.get("freq_hz", _DEFAULT_SERVO_HZ))
                servo_min_us = int(mod.params.get("min_us", 500))
                servo_max_us = int(mod.params.get("max_us", 2500))
            elif mod.module == "gpio_out":
                gpio_pins += list(mod.pins)
                gpio_initial = int(mod.params.get("initial", 0))
            elif mod.module == "matrix_scan":
                frame_sources.append((3, 0, 0, 0))
                scan = {
                    "rows": int(mod.params.get("rows", 16)),
                    "max_code": int(mod.params.get("max_code", 65535)),
                    "sel_pins": list(mod.pins[:3]),
                    "inh_pins": list(mod.pins[3:]),
                    "dac_pin": mod.params["dac_pin"],
                    "ack_pins": list(mod.params.get("ack_pins") or []),
                    "settle_s": round(int(mod.params.get("settle_ms", 2)) / 1000.0, 4),
                    "ack_timeout_s": round(int(mod.params.get("ack_timeout_ms", 50)) / 1000.0, 4),
                }
            elif mod.module == "scan_follower":
                frame_sources.append((3, 0, 0, 0))
                follower = {
                    "rows": int(mod.params.get("rows", 16)),
                    "max_code": int(mod.params.get("max_code", 65535)),
                    "watch_pin": mod.params["watch_pin"],
                    "ack_pin": mod.params["ack_pin"],
                    "settle_s": round(int(mod.params.get("settle_ms", 2)) / 1000.0, 4),
                    "watch_timeout_s": round(int(mod.params.get("watch_timeout_ms", 250)) / 1000.0, 4),
                }

        if not frame_sources and not pwm_pins and not servo_pins and not gpio_pins:
            raise BuildError(f"{target.id}: no sensor channels or output pins configured")

        period = round(1.0 / max(1, sample_hz), 3)
        src_root = contract_mod.source_root(target, root)
        env = Environment(
            loader=FileSystemLoader(str(src_root / "templates")),
            undefined=StrictUndefined, keep_trailing_newline=True,
        )
        if follower:
            loop_sleep = _FOLLOWER_LOOP_SLEEP   # paced by awaiting the conductor
        elif frame_sources:
            loop_sleep = period
        else:
            loop_sleep = _CMD_LOOP_SLEEP
        code = env.get_template("code.py.j2").render(
            id=target.id, target=target.target, board=target.board,
            addrs=addrs, has_ads=bool(addrs), tach_pins=tach_pins, ppr=ppr,
            analog_pins=analog_pins,
            scan=scan, follower=follower,
            frame_sources=frame_sources,
            pwm_pins=pwm_pins, pwm_freq=pwm_freq,
            servo_pins=servo_pins, servo_freq=servo_freq,
            servo_min_us=servo_min_us, servo_max_us=servo_max_us,
            gpio_pins=gpio_pins, gpio_initial=gpio_initial,
            period=period,
            loop_sleep=loop_sleep,
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
