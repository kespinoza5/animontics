from __future__ import annotations

import logging
from pathlib import Path

from core.effector_base import EffectorBase, register_effector
from core.mcu_link import CMD_SET_US

log = logging.getLogger(__name__)


class SysfsPwm:
    """Minimal Linux hardware-PWM driver (/sys/class/pwm) for the sbc_pwm backend.

    One instance per pwmchip; lines are lazily exported. Pulse widths are
    written as duty_cycle in ns against a fixed period (the servo frame rate).
    `root` is injectable for tests.
    """

    def __init__(self, chip: int, freq_hz: int, root: str = "/sys/class/pwm") -> None:
        self._chip = Path(root) / f"pwmchip{chip}"
        self._period_ns = round(1_000_000_000 / freq_hz)
        self._exported: set[int] = set()

    def _line_dir(self, line: int) -> Path:
        return self._chip / f"pwm{line}"

    def _ensure(self, line: int) -> Path:
        d = self._line_dir(line)
        if line not in self._exported:
            if not d.exists():
                (self._chip / "export").write_text(str(line))
            (d / "period").write_text(str(self._period_ns))
            (d / "enable").write_text("1")
            self._exported.add(line)
        return d

    def set_us(self, line: int, us: int) -> bool:
        try:
            d = self._ensure(line)
            (d / "duty_cycle").write_text(str(us * 1000))
            return True
        except OSError as exc:
            log.warning("sbc_pwm line %d: %s", line, exc)
            self._exported.discard(line)
            return False

    def disable(self, line: int) -> None:
        try:
            (self._line_dir(line) / "enable").write_text("0")
        except OSError:
            pass
        self._exported.discard(line)


@register_effector("servo")
class ServoEffector(EffectorBase):
    """Hobby servos — position by angle (or raw µs), over two backends.

    Request body, one or both of:
        {"angles": {channel: degrees}}     — mapped through the channel's
                                             deg↔µs calibration, soft-limited
        {"us":     {channel: microseconds}} — raw, clamped to [min_us, max_us]
    `channel` may be a name or an index.

    Backend (config.backend):
        {kind: mcu, device: <id>}   — send_command(CMD_SET_US, [index, us])
                                      through an MCU running servo_out firmware
        {kind: sbc_pwm, chip: N}    — Linux hardware PWM (/sys/class/pwm);
                                      channel index = pwm line on that chip

    Params (global, each overridable per channel via params.per_channel.<name>):
        freq_hz (50), min_us (500), max_us (2500) — pulse bounds
        deg_min (0), deg_max (180)                — travel soft limits
        trim_deg (0)                              — added to every angle
        invert (false)                            — reverse direction

    The angle→µs map and limits live HERE, in config — the firmware only
    moves microseconds (and applies its own absolute safety clamp).
    """

    effector_type = "servo"
    lanes = ("request",)

    def __init__(self, effector_id, config) -> None:
        super().__init__(effector_id, config)
        p = config.params or {}
        self._freq = int(p.get("freq_hz", 50))
        self._pwm: SysfsPwm | None = None
        if config.backend.get("kind") == "sbc_pwm":
            self._pwm = SysfsPwm(int(config.backend.get("chip", 0)), self._freq,
                                 root=config.backend.get("root", "/sys/class/pwm"))

    # ── Calibration ───────────────────────────────────────────────────────────

    def _cal(self, name: str) -> dict:
        p = self.config.params or {}
        cal = {
            "min_us": float(p.get("min_us", 500)),
            "max_us": float(p.get("max_us", 2500)),
            "deg_min": float(p.get("deg_min", 0.0)),
            "deg_max": float(p.get("deg_max", 180.0)),
            "trim_deg": float(p.get("trim_deg", 0.0)),
            "invert": bool(p.get("invert", False)),
        }
        cal.update((p.get("per_channel") or {}).get(name) or {})
        return cal

    def _angle_to_us(self, deg: float, cal: dict) -> int:
        deg = max(cal["deg_min"], min(cal["deg_max"], deg + cal["trim_deg"]))
        if cal["invert"]:
            deg = cal["deg_max"] - (deg - cal["deg_min"])
        span = cal["deg_max"] - cal["deg_min"] or 1.0
        frac = (deg - cal["deg_min"]) / span
        return round(cal["min_us"] + frac * (cal["max_us"] - cal["min_us"]))

    def _clamp_us(self, us: float, cal: dict) -> int:
        return round(max(cal["min_us"], min(cal["max_us"], us)))

    # ── Drive ─────────────────────────────────────────────────────────────────

    def _write(self, index: int, us: int) -> bool:
        if self._pwm is not None:
            return self._pwm.set_us(index, us)
        return self._device is not None and self._device.send_command(
            CMD_SET_US, [index, us]
        )

    def handle_request(self, payload: dict) -> dict:
        angles = payload.get("angles") or {}
        raw_us = payload.get("us") or {}
        if not angles and not raw_us:
            return {"error": "expected {'angles': {channel: deg}} and/or "
                             "{'us': {channel: microseconds}}"}
        results: dict[str, str] = {}
        for source, by_angle in ((angles, True), (raw_us, False)):
            for key, value in source.items():
                ch = self._channel(key)
                if ch is None:
                    results[str(key)] = "unknown channel"
                    continue
                cal = self._cal(ch.name)
                us = (self._angle_to_us(float(value), cal) if by_angle
                      else self._clamp_us(float(value), cal))
                ok = self._write(ch.index, us)
                self._state[ch.name] = {"deg": round(float(value), 2), "us": us} \
                    if by_angle else {"us": us}
                results[ch.name] = "ok" if ok else "link down"
        return {"set": results}

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["value"] = "degrees (angles) / microseconds (us)"
        d["limits"] = {c.name: {k: v for k, v in self._cal(c.name).items()}
                       for c in self.channels}
        return d

    def stop(self) -> None:
        if self._pwm is not None:
            for ch in self.channels:
                self._pwm.disable(ch.index)
