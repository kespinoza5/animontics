"""
IR transceiver sensor — TSOP38238 receiver + TSAL6200 emitter via Linux LIRC.

Hardware
--------
  RX: TSOP38238 on PH10/IR_RX  → /dev/lirc0  (sun4i-ir hardware decoder)
  TX: TSAL6200  on PH0/PWM3    → /dev/lirc1  (pwm-ir-tx overlay)

Both devices are optional; the sensor degrades gracefully when either is
absent (see can_receive / can_transmit properties).

Config connection fields (type: ir)
-------------------------------------
  rx_device: /dev/lirc0   # omit to disable RX
  tx_device: /dev/lirc1   # omit to disable TX

SensorReading data fields
--------------------------
  protocol : str   — "NEC" | "NECX" | "NEC32" | "RC5" | "PROTO_N"
  address  : int   — decoded device address
  command  : int   — decoded command byte
  scancode : int   — kernel-style: (address << 8) | command for NEC family
  repeat   : bool  — True when this is a held-key repeat frame
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
import sensors.ir_xcvr.driver as _drv
from sensors.ir_xcvr.codec import decode_nec

log = logging.getLogger(__name__)

_READ_TIMEOUT_S = 0.5    # select() wait before checking stop event
_FRAME_GAP_US   = 10_000 # mode2: gap > 10 ms marks a new frame


@register("ir_xcvr")
class IrXcvrSensor(SensorBase):
    """
    IR transceiver sensor wrapping TSOP38238 (RX) and TSAL6200 (TX).

    Config example::

        - id: ir_xcvr
          type: ir_xcvr
          enabled: true
          connection:
            type: ir
            rx_device: /dev/lirc0
            tx_device: /dev/lirc1
    """

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)

        conn = config.connection
        self._rx_device: str | None = getattr(conn, "rx_device", None)
        self._tx_device: str | None = getattr(conn, "tx_device", None)

        self._thread:      threading.Thread | None = None
        self._stop_event = threading.Event()
        self._healthy    = False

        self._tx_fd:            int | None = None
        self._tx_scancode_mode: bool       = False
        self._tx_lock = threading.Lock()

    # ── SensorBase interface ──────────────────────────────────────────────────

    def start(self) -> None:
        self._stop_event.clear()

        if self._tx_device:
            self._open_tx()

        if self._rx_device:
            self._thread = threading.Thread(
                target=self._read_loop, daemon=True, name=f"sensor-{self.id}"
            )
            self._thread.start()
        else:
            log.info("%s: no rx_device configured — RX disabled", self.id)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._close_tx()
        self._healthy = False

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy

    # ── Capability flags (queried by the router) ──────────────────────────────

    @property
    def can_receive(self) -> bool:
        return bool(self._rx_device)

    @property
    def can_transmit(self) -> bool:
        with self._tx_lock:
            return self._tx_fd is not None

    # ── TX public API ─────────────────────────────────────────────────────────

    def transmit(self, protocol: str, address: int, command: int) -> bool:
        """
        Transmit one IR code.

        Parameters
        ----------
        protocol : "NEC" or "NECX"
        address  : 0-255 (NEC) / 0-65535 (NECX)
        command  : 0-255

        Returns
        -------
        bool  True on success; False if TX unavailable or the write failed.
        """
        with self._tx_lock:
            if self._tx_fd is None:
                log.warning("%s: transmit called but TX device is not open", self.id)
                return False
            try:
                if self._tx_scancode_mode:
                    return _drv.write_scancode(self._tx_fd, protocol, address, command)
                else:
                    from sensors.ir_xcvr.codec import encode_nec
                    pulses = encode_nec(address, command, extended=(protocol.upper() == "NECX"))
                    return _drv.write_raw_pulses(self._tx_fd, pulses)
            except OSError as exc:
                log.error("%s: TX write failed — %s", self.id, exc)
                return False

    # ── TX device lifecycle ───────────────────────────────────────────────────

    def _open_tx(self) -> None:
        try:
            fd, scancode_mode = _drv.open_lirc_tx(self._tx_device)
        except OSError as exc:
            log.warning("%s: cannot open TX device %s — %s", self.id, self._tx_device, exc)
            return
        mode_label = "scancode" if scancode_mode else "raw pulse"
        log.info("%s: TX %s opened (%s mode)", self.id, self._tx_device, mode_label)
        with self._tx_lock:
            self._tx_fd            = fd
            self._tx_scancode_mode = scancode_mode

    def _close_tx(self) -> None:
        with self._tx_lock:
            if self._tx_fd is not None:
                _drv.close_lirc(self._tx_fd)
                self._tx_fd = None

    # ── RX read loop ──────────────────────────────────────────────────────────

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._open_and_read()
            except Exception as exc:
                self._healthy = False
                log.warning("%s: RX error — %s — retrying in 2 s", self.id, exc)
                self._stop_event.wait(2)
        self._healthy = False

    def _open_and_read(self) -> None:
        fd, scancode_mode = _drv.open_lirc_rx(self._rx_device)
        mode_label = "scancode" if scancode_mode else "mode2"
        log.info("%s: RX %s opened (%s mode)", self.id, self._rx_device, mode_label)
        self._healthy = True
        try:
            if scancode_mode:
                self._read_scancode(fd)
            else:
                self._read_mode2(fd)
        finally:
            _drv.close_lirc(fd)
            self._healthy = False

    def _read_scancode(self, fd: int) -> None:
        import select
        while not self._stop_event.is_set():
            ready, _, _ = select.select([fd], [], [], _READ_TIMEOUT_S)
            if not ready:
                continue
            result = _drv.read_one_scancode(fd)
            if result is None:
                continue
            protocol, address, command, scancode, repeat = result
            self._emit(protocol, address, command, scancode, repeat)

    def _read_mode2(self, fd: int) -> None:
        import select
        pulses: list[int] = []

        while not self._stop_event.is_set():
            ready, _, _ = select.select([fd], [], [], _READ_TIMEOUT_S)

            if not ready:
                if pulses:
                    self._decode_and_emit_mode2(pulses)
                    pulses = []
                continue

            result = _drv.read_one_mode2_word(fd)
            if result is None:
                continue

            kind, duration = result

            if kind == "timeout":
                if pulses:
                    self._decode_and_emit_mode2(pulses)
                    pulses = []
                continue

            if duration > _FRAME_GAP_US and pulses:
                self._decode_and_emit_mode2(pulses)
                pulses = []

            pulses.append(duration)

    def _decode_and_emit_mode2(self, pulses: list[int]) -> None:
        result = decode_nec(pulses)
        if result is None:
            log.debug("%s: mode2 decode failed (%d pulses)", self.id, len(pulses))
            return
        self._emit(result.protocol, result.address, result.command,
                   result.scancode, result.repeat)

    # ── Emit helper ───────────────────────────────────────────────────────────

    def _emit(
        self,
        protocol: str,
        address:  int,
        command:  int,
        scancode: int,
        repeat:   bool,
    ) -> None:
        data: dict[str, Any] = {
            "protocol": protocol,
            "address":  address,
            "command":  command,
            "scancode": scancode,
            "repeat":   repeat,
        }
        reading = SensorReading(
            sensor_id=self.id,
            sensor_type="ir_xcvr",
            timestamp=time.time(),
            data=data,
        )
        log.debug(
            "%s: RX %s addr=0x%04X cmd=0x%02X repeat=%s",
            self.id, protocol, address, command, repeat,
        )
        self._broadcast(reading)
