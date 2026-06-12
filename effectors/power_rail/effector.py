from __future__ import annotations

import logging

from core.effector_base import EffectorBase, register_effector
from core.gpio import NullOutputLine, OutputLine, make_output_line

log = logging.getLogger(__name__)


@register_effector("power_rail")
class PowerRail(EffectorBase):
    """One switchable power rail (relay / high-side switch) — gating, not failure.

    Request body (request lane):
        {"on": true|false}                — direct switch
        {"levels": {<channel>: 0|1}}      — policy lane (PolicyRuntime applies
                                            actions as levels; >= 0.5 = on)

    Backend (config.backend):
        {kind: gpio, line: {backend: libgpiod, chip, line, active_low}}
            — SBC kernel GPIO driving the relay IN pin. Most SRD-05VDC
              modules energize on LOW: put active_low in the line spec.
        {kind: mcu, device: <id>, channel: N, active_low: …}
            — a gpio_out firmware channel via the device's command sink
              (core/gpio.py mcu backend; e.g. the brainstem RP2040s).

    Config keys (params):
        initial: "on"|"off"  (default "on") — state applied at startup
        members: [device ids]              — devices powered THROUGH this rail.
            While the rail is off those devices are *gated*: GET /devices
            reports them gated (not failed), so a deliberate power cut never
            reads as a fault. The mcu_serial reconnect loop picks them back
            up when the rail returns.

    Rail state is published to the thalamic relay as `power.<id>` (1/0) so
    policies and other cortices can observe gating like any other signal.
    """

    effector_type = "power_rail"
    lanes = ("request",)

    def __init__(self, effector_id, config) -> None:
        super().__init__(effector_id, config)
        self._line: OutputLine = NullOutputLine("not attached")
        self._relay = None
        self._on: bool | None = None          # unknown until start()

    # ── Binding ───────────────────────────────────────────────────────────────

    def attach_devices(self, devices) -> None:
        super().attach_devices(devices)
        b = self.config.backend or {}
        if b.get("kind") == "mcu":
            spec = {"backend": "mcu", "device": b.get("device"),
                    "channel": b.get("channel", 0),
                    "active_low": b.get("active_low", False)}
        else:
            spec = b.get("line")
        self._line = make_output_line(spec, devices=devices)

    def attach_relay(self, relay) -> None:
        """Optional app.py hook — lets the rail publish its state as a signal."""
        self._relay = relay

    # ── Switching ─────────────────────────────────────────────────────────────

    @property
    def members(self) -> list[str]:
        return list(self.config.params.get("members") or [])

    def is_on(self) -> bool | None:
        return self._on

    def gated_devices(self) -> set[str]:
        """Device ids currently without power because this rail is off."""
        return set(self.members) if self._on is False else set()

    def set_on(self, on: bool) -> None:
        self._line.set(bool(on))
        self._on = bool(on)
        self._state["on"] = self._on
        if self._relay is not None:
            self._relay.publish(f"power.{self.id}", 1 if self._on else 0)
        log.info("power_rail %s: %s (members: %s)",
                 self.id, "ON" if on else "OFF", ", ".join(self.members) or "—")

    def handle_request(self, payload: dict) -> dict:
        if "on" in payload:
            self.set_on(bool(payload["on"]))
            return {"set": {"on": self._on}}
        levels = payload.get("levels")
        if isinstance(levels, dict) and levels:
            # Policy lane: any addressed channel sets the whole rail.
            value = next(iter(levels.values()))
            self.set_on(float(value) >= 0.5)
            return {"set": {"on": self._on}}
        return {"error": "expected {'on': bool} or {'levels': {channel: 0|1}}"}

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["value"] = "on/off"
        d["members"] = self.members
        return d

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self.set_on(str(self.config.params.get("initial", "on")).lower() != "off")

    def stop(self) -> None:
        # Deliberately leave the rail as-is: a node restart must not cut power
        # to peripherals. Releasing the GPIO is the only cleanup.
        self._line.close()
