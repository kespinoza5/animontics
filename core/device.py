"""Devices — shared peripherals that sensors read through and effectors write through.

A device owns a transport that is shared across directions or across several
logical sensors/effectors, so neither a sensor nor an effector may own it:

  • McuSerialDevice — an MCU's serial link. Push model: a read pump decodes
    core.mcu_link frames and fans them out to subscribers (sensors); effectors
    send command frames back over the same link via send_command().
  • Ads1115Device   — an ADS1115 ADC chip (added in Phase D). Pull model:
    serialized muxed reads of individual channels.

Devices are created from config at node startup and held on app.state.devices;
sensors/effectors bind to them by id. pyserial is imported lazily so core/ stays
importable on machines without it.
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.mcu_link import Frame, FrameStream, encode_command

if TYPE_CHECKING:
    from core.models import DeviceConfig

log = logging.getLogger(__name__)

_registry: dict[str, type["Device"]] = {}


def register_device(kind: str):
    """Class decorator registering a Device subclass under a `kind` key."""
    def decorator(cls: type["Device"]) -> type["Device"]:
        cls.kind = kind
        _registry[kind] = cls
        return cls
    return decorator


def create_device(config: "DeviceConfig") -> "Device":
    """Instantiate a device from its config. Raises ValueError for unknown kinds."""
    cls = _registry.get(config.kind)
    if cls is None:
        raise ValueError(
            f"Unknown device kind '{config.kind}'. Known: {sorted(_registry)}."
        )
    return cls(config.id, config)


class Device(ABC):
    """Base class for shared peripherals."""

    kind: str = ""

    def __init__(self, device_id: str, config: "DeviceConfig") -> None:
        self.id = device_id
        self.config = config

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def is_healthy(self) -> bool: ...


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
