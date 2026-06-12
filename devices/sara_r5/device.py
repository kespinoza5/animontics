"""SaraR5Device — u-blox SARA-R5 LTE-M/NB-IoT modem with integrated GNSS, over UART.

Mixed model — one physical module on one UART serves two logical sensors:
  • GNSS  — NMEA sentences ($Gx…) are pushed to subscribe_gnss() callbacks as they
            arrive (sara_r5_gnss reads these).
  • LTE   — signal/registration status is polled on demand via send_at()
            (sara_r5_lte reads these). send_at() is also the public seam for
            future SIM / SMS / data use.

The modem's power-enable and reset pins are driven through core.gpio output lines,
so the same device works whether those pins hang off an Orange Pi, a Pi 5, or
(later) an MCU — the board config picks the backend. pyserial is imported lazily.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.device import Device, register_device
from core.gpio import make_output_line

if TYPE_CHECKING:
    from core.models import DeviceConfig

log = logging.getLogger(__name__)

# AT responses end with a final result line; treat these as terminators.
_AT_TERMINATORS = ("OK", "ERROR")
_AT_ERROR_PREFIXES = ("+CME ERROR", "+CMS ERROR")
# Lines routed to GNSS subscribers rather than the AT accumulator.
_GNSS_PREFIXES = ("$", "+UULOC:")

# Default GNSS enable: AT+UGPS=1,1 → power on, all NMEA sentences.
_DEFAULT_INIT = ["ATE0", "AT+CMEE=2", "AT+CEREG=2", "AT+UGPS=1,1"]


@register_device("sara_r5")
class SaraR5Device(Device):
    """u-blox SARA-R5 modem over UART.

    DeviceConfig fields:
      port   — UART device path, e.g. /dev/ttyS5
      baud   — baud rate (default 115200)
      params:
        power_line — core.gpio spec for the LTE power-enable pin (optional)
        reset_line — core.gpio spec for the reset pin (optional)
        init       — list of AT commands sent on connect (default enables GNSS)
        power_on_delay_s / reset_settle_s — timing overrides (optional)
    """

    BAUD_DEFAULT = 115_200

    SPEC = {
        "description": "u-blox SARA-R5 modem — NMEA push + AT poll over one UART.",
        "required": ["port"],
        "optional": ["baud"],
        "params": ["init", "power_on_delay_s", "reset_settle_s",
                   "power_line", "reset_line"],
    }

    def __init__(self, device_id: str, config: "DeviceConfig") -> None:
        super().__init__(device_id, config)
        params = config.params or {}
        self._init_cmds: list[str] = list(params.get("init", _DEFAULT_INIT))
        self._power_on_delay = float(params.get("power_on_delay_s", 1.0))
        self._reset_settle = float(params.get("reset_settle_s", 3.0))

        # Pin control is backend-agnostic (libgpiod / mcu / null) — see core.gpio.
        self._power_line = make_output_line(params.get("power_line"))
        self._reset_line = make_output_line(params.get("reset_line"))

        self._gnss_subs: list[Callable[[str], None]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._healthy = False

        # AT engine — one command outstanding at a time.
        self._at_lock = threading.Lock()
        self._at_buf: list[str] = []
        self._at_ready = threading.Event()
        self._ser = None
        self._write_lock = threading.Lock()

    # ── Subscription (GNSS sensor) ────────────────────────────────────────────

    def subscribe_gnss(self, callback: Callable[[str], None]) -> None:
        """Register a callback invoked (in the read thread) for each NMEA sentence."""
        self._gnss_subs.append(callback)

    # ── AT command sink (LTE sensor; future SIM use) ──────────────────────────

    def send_at(self, cmd: str, timeout: float = 5.0) -> list[str]:
        """Send an AT command; return the response lines (excluding the final
        OK/ERROR terminator). Thread-safe. Returns [] on timeout or a down link."""
        with self._at_lock:
            self._at_buf = []
            self._at_ready.clear()
            with self._write_lock:
                ser = self._ser
                if ser is None:
                    return []
                try:
                    ser.write(f"{cmd}\r\n".encode())
                except OSError as exc:
                    log.warning("device %s: AT write failed — %s", self.id, exc)
                    return []
            if not self._at_ready.wait(timeout):
                log.warning("device %s: AT timeout for %r", self.id, cmd)
                return []
            return [
                ln for ln in self._at_buf
                if ln not in _AT_TERMINATORS
                and not ln.startswith(_AT_ERROR_PREFIXES)
            ]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"device-{self.id}"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._power_line.close()
        self._reset_line.close()

    def is_healthy(self) -> bool:
        return self._healthy

    # ── Power / reset (via core.gpio) ─────────────────────────────────────────

    def _power_on(self) -> None:
        log.info("device %s: asserting LTE power-enable", self.id)
        self._power_line.set(True)
        self._stop.wait(self._power_on_delay)

    def reset_modem(self) -> None:
        """Pulse the reset line low→high and wait for the modem to boot."""
        log.info("device %s: pulsing reset", self.id)
        self._reset_line.set(False)
        self._stop.wait(0.1)
        self._reset_line.set(True)
        self._stop.wait(self._reset_settle)

    # ── Main thread ───────────────────────────────────────────────────────────

    def _run(self) -> None:
        import serial  # lazy: hardware dep

        self._power_on()
        port = self.config.port or "/dev/ttyS5"
        baud = self.config.baud or self.BAUD_DEFAULT

        while not self._stop.is_set():
            try:
                with serial.Serial(port, baud, timeout=1) as ser:
                    self._ser = ser
                    log.info("device %s: opened %s at %d baud", self.id, port, baud)
                    self._healthy = True
                    self._read_loop(ser)
            except serial.SerialException as exc:
                self._healthy = False
                log.warning("device %s: serial error — %s — retrying in 5s", self.id, exc)
                self._stop.wait(5)
            finally:
                self._ser = None

        self._healthy = False

    def _send_init(self) -> None:
        # The modem may still be emitting +STARTUP; give it a moment before AT.
        self._stop.wait(2)
        for cmd in self._init_cmds:
            self.send_at(cmd)
        log.info("device %s: init sequence sent (%d cmds)", self.id, len(self._init_cmds))

    def _read_loop(self, ser) -> None:
        # Kick off init from a worker so the read loop is already draining the port
        # (send_at depends on this loop to deliver the OK/ERROR terminator).
        threading.Thread(target=self._send_init, daemon=True,
                          name=f"device-{self.id}-init").start()
        buf = b""
        while not self._stop.is_set():
            chunk = ser.read(256)
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.rstrip(b"\r").decode("ascii", errors="replace").strip()
                if line:
                    self._route(line)

    def _route(self, line: str) -> None:
        if line.startswith(_GNSS_PREFIXES):
            for cb in self._gnss_subs:
                try:
                    cb(line)
                except Exception:
                    log.exception("device %s: gnss subscriber error", self.id)
            return
        # AT response: accumulate until a terminator releases the waiter.
        self._at_buf.append(line)
        if line in _AT_TERMINATORS or line.startswith(_AT_ERROR_PREFIXES):
            self._at_ready.set()
