"""McuSerialDevice — an MCU on a serial link.

Push model: a read pump decodes core.mcu_link frames and fans them out to
subscribers (sensors); effectors send command frames back over the same link via
send_command(). pyserial is imported lazily so the package stays importable on
machines without it.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.device import Device, register_device
from core.mcu_link import Frame, FrameStream, encode_command

if TYPE_CHECKING:
    from core.models import DeviceConfig

log = logging.getLogger(__name__)


@register_device("mcu_serial")
class McuSerialDevice(Device):
    """An MCU on a serial link: streams sample frames in, takes command frames out."""

    BAUD_DEFAULT = 115_200
    DEFAULT_PORT = "/dev/ttyUSB0"

    def __init__(self, device_id: str, config: "DeviceConfig") -> None:
        super().__init__(device_id, config)
        self._subscribers: list[Callable[[Frame], None]] = []
        self._ser = None
        self._write_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._healthy = False

    # ── Subscription (sensors) ────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[Frame], None]) -> None:
        """Register a callback invoked (in the read thread) for every decoded frame."""
        self._subscribers.append(callback)

    # ── Command sink (effectors) ──────────────────────────────────────────────

    def send_command(self, cmd_id: int, args=()) -> bool:
        """Send a command frame to the MCU. Returns False if the link is down."""
        ser = self._ser
        if ser is None:
            return False
        payload = encode_command(cmd_id, list(args))
        with self._write_lock:
            try:
                ser.write(payload)
                return True
            except OSError as exc:              # pyserial SerialException is an OSError
                log.warning("device %s: command write failed — %s", self.id, exc)
                return False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_pump, daemon=True, name=f"device-{self.id}"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)

    def is_healthy(self) -> bool:
        return self._healthy

    # ── Read pump ─────────────────────────────────────────────────────────────

    def _read_pump(self) -> None:
        import serial  # lazy: hardware dep

        port = self.config.port or self.DEFAULT_PORT
        baud = self.config.baud or self.BAUD_DEFAULT
        stream = FrameStream()

        while not self._stop_event.is_set():
            try:
                with serial.Serial(port, baud, timeout=1) as ser:
                    log.info("device %s: opened %s at %d baud", self.id, port, baud)
                    self._healthy = True
                    self._ser = ser
                    while not self._stop_event.is_set():
                        chunk = ser.read(64)
                        if not chunk:
                            continue
                        for frame in stream.feed(chunk):
                            self._dispatch(frame)
            except serial.SerialException as exc:
                self._healthy = False
                log.warning("device %s: serial error — %s — retrying in 2s", self.id, exc)
                self._stop_event.wait(2)
            finally:
                self._ser = None

        self._healthy = False

    def _dispatch(self, frame: Frame) -> None:
        for callback in self._subscribers:
            try:
                callback(frame)
            except Exception:                  # one bad subscriber must not kill the pump
                log.exception("device %s: subscriber error", self.id)
