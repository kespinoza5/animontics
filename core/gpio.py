"""Portable digital output lines — for devices that toggle SBC/MCU pins.

A device (e.g. the SARA-R5 modem's LTE power / reset pins) must not hard-code
*how* a pin is driven. On an Orange Pi or a Raspberry Pi 5 it is a kernel GPIO
line via libgpiod (the modern character-device interface — `/sys/class/gpio`
sysfs is deprecated and disabled on many mainline kernels). In the future the same
modem could be power-gated by an MCU's command channel instead. So a device asks
for an `OutputLine` from a small spec dict and just calls `.set(value)`.

Spec shape (from a device's `params` in the board config):

    {backend: libgpiod, chip: "gpiochip1", line: 262, active_low: false}
    {backend: mcu, device: "<id>", command: 0x10, channel: 0}   # future seam
    {backend: none}                                              # explicit no-op

`backend` defaults to `libgpiod`. Backends are looked up by name; gpiod is
lazy-imported so dev machines and boards without it stay importable. If a line
can't be opened, `make_output_line` returns a `NullOutputLine` (logged) rather
than raising — a missing power pin should degrade to "modem assumed powered", not
crash the node.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

log = logging.getLogger(__name__)


class OutputLine(ABC):
    """A single digital output a device can drive high/low."""

    @abstractmethod
    def set(self, value: bool) -> None:
        """Drive the line; True = active (respecting active_low)."""

    def close(self) -> None:
        """Release the line. Default no-op; backends override as needed."""


class NullOutputLine(OutputLine):
    """No-op line — used when no pin is wired or a backend is unavailable."""

    def __init__(self, reason: str = "") -> None:
        self._reason = reason

    def set(self, value: bool) -> None:
        log.debug("gpio: ignoring set(%s) — %s", value, self._reason or "no line")

    def close(self) -> None:
        pass


class LibgpiodOutputLine(OutputLine):
    """A kernel GPIO output driven through libgpiod's character device.

    Supports both the v2 (`gpiod.request_lines`) and v1 (`gpiod.Chip`/`get_line`)
    Python bindings — Armbian/Debian releases ship different majors. `chip` is a
    gpiochip name (`"gpiochip1"`) or path (`"/dev/gpiochip1"`) or label; `line` is
    the line offset within that chip.

    NOTE: unverified on the Orange Pi Zero 2 target yet — the line offset for a
    sunxi pin and the gpiochip numbering need confirming on hardware. See TODO.md.
    """

    def __init__(self, chip: str, line: int, active_low: bool = False,
                 consumer: str = "animontics") -> None:
        import gpiod  # lazy hardware dep

        self._req = None          # v2 request handle
        self._line_obj = None     # v1 line handle
        self._line = line
        path = chip if chip.startswith("/dev/") else f"/dev/{chip}"

        if hasattr(gpiod, "request_lines"):                 # libgpiod v2
            from gpiod.line import Direction, Value
            self._Value = Value
            settings = gpiod.LineSettings(
                direction=Direction.OUTPUT,
                active_low=active_low,
                output_value=Value.INACTIVE,
            )
            self._req = gpiod.request_lines(
                path, consumer=consumer, config={line: settings}
            )
        else:                                               # libgpiod v1
            self._chip = gpiod.Chip(chip)
            self._line_obj = self._chip.get_line(line)
            flags = gpiod.LINE_REQ_FLAG_ACTIVE_LOW if active_low else 0
            self._line_obj.request(
                consumer=consumer, type=gpiod.LINE_REQ_DIR_OUT,
                flags=flags, default_vals=[0],
            )

    def set(self, value: bool) -> None:
        if self._req is not None:                           # v2
            self._req.set_value(
                self._line, self._Value.ACTIVE if value else self._Value.INACTIVE
            )
        elif self._line_obj is not None:                    # v1
            self._line_obj.set_value(1 if value else 0)

    def close(self) -> None:
        try:
            if self._req is not None:
                self._req.release()
            elif self._line_obj is not None:
                self._line_obj.release()
        except Exception:
            pass


def make_output_line(spec: dict[str, Any] | None) -> OutputLine:
    """Build an `OutputLine` from a spec dict.

    Returns a `NullOutputLine` (never raises) when no pin is configured or the
    backend can't be opened — failures are logged. `backend` defaults to
    `libgpiod`; `none`/`null` force a no-op; `mcu` is a documented seam.
    """
    if not spec:
        return NullOutputLine("no spec")

    backend = spec.get("backend", "libgpiod")

    if backend in ("none", "null"):
        return NullOutputLine("backend=none")

    if backend == "libgpiod":
        try:
            return LibgpiodOutputLine(
                chip=str(spec["chip"]),
                line=int(spec["line"]),
                active_low=bool(spec.get("active_low", False)),
            )
        except KeyError as exc:
            log.warning("gpio: libgpiod spec missing %s — %s", exc, spec)
            return NullOutputLine(f"missing key {exc}")
        except Exception as exc:                            # no gpiod, bad chip/line, busy
            log.warning("gpio: libgpiod line unavailable (%s) — %s", exc, spec)
            return NullOutputLine(f"libgpiod error: {exc}")

    if backend == "mcu":
        # Seam: drive a pin through a device's command sink (e.g. an MCU GPIO).
        # Not implemented — the modem can also be wired to power on by default.
        log.warning("gpio: 'mcu' backend not implemented yet — %s", spec)
        return NullOutputLine("mcu backend stub")

    log.warning("gpio: unknown backend %r — %s", backend, spec)
    return NullOutputLine(f"unknown backend {backend}")
