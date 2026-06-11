from __future__ import annotations

import logging
import threading
import time

import smbus2

from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
from sensors.vl53l1x.driver import VL53L1X

log = logging.getLogger(__name__)

# Display metadata per ranging mode (driver owns the register values).
_MODES: dict[int, dict] = {
    1: {"label": "short",  "max_mm": 1300},
    2: {"label": "medium", "max_mm": 2000},
    3: {"label": "long",   "max_mm": 4000},
}

# Auto-ranging step thresholds (mm). The gap between the up/down edges of a
# given mode is the hysteresis deadband that stops the mode oscillating when a
# reading sits on a boundary. One step per reading keeps switches gradual.
_AUTO_UP   = {1: 1150, 2: 1850}   # above this → step to the next *longer* mode
_AUTO_DOWN = {2: 950,  3: 1650}   # below this → step to the next *shorter* mode


@register("vl53l1x")
class VL53L1XSensor(SensorBase):
    """
    ST VL53L1X time-of-flight distance sensor over I2C.

    Config connection fields:
      type:    i2c
      bus:     3         (I2C bus number, e.g. /dev/i2c-3)
      address: 0x29      (default VL53L1X address)

    Ranging modes (1=short ~1.3 m, 2=medium ~2 m, 3=long ~4 m) trade maximum
    range for speed and ambient-light immunity. The sensor starts in long mode.
    Two runtime controls are exposed (via node/routers/vl53l1x.py):

      set_mode(m)  — pin a fixed mode (also turns auto off)
      set_auto(on) — let the sensor pick the tightest mode that covers the
                     current distance, with hysteresis to prevent flapping

    Both are thread-safe: the caller only stages intent; the background read
    loop is the single thread that ever touches the I2C bus.
    """

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._healthy = False

        self._lock = threading.Lock()
        self._mode = 3                 # currently applied mode (loop writes only)
        self._auto = False
        self._pending_mode: int | None = None   # staged by set_mode()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop, daemon=True, name=f"sensor-{self.id}"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy

    # ── Runtime controls (called from request handlers) ───────────────────────

    @property
    def mode(self) -> int:
        return self._mode

    @property
    def auto(self) -> bool:
        return self._auto

    def mode_info(self) -> dict:
        """Current control state — used by the state endpoint and named events."""
        with self._lock:
            m = self._mode
            return {
                "mode":   m,
                "label":  _MODES[m]["label"],
                "max_mm": _MODES[m]["max_mm"],
                "auto":   self._auto,
            }

    def set_mode(self, mode: int) -> None:
        """Pin a fixed ranging mode (1/2/3). Disables auto-ranging."""
        if mode not in _MODES:
            raise ValueError(f"mode must be one of {sorted(_MODES)}, got {mode!r}")
        with self._lock:
            self._auto = False
            self._pending_mode = mode

    def set_auto(self, enabled: bool) -> None:
        """Enable or disable distance-driven auto mode selection."""
        with self._lock:
            self._auto = bool(enabled)
        # Reflect the toggle immediately; mode changes broadcast as they apply.
        self._broadcast_event("mode", self.mode_info())

    @staticmethod
    def _auto_step(mode: int, mm: int) -> int:
        """Pick the next mode (at most one step) for an auto-ranging reading."""
        if mode < 3 and mm > _AUTO_UP[mode]:
            return mode + 1
        if mode > 1 and mm < _AUTO_DOWN[mode]:
            return mode - 1
        return mode

    # ── Background reading loop ───────────────────────────────────────────────

    def _read_loop(self) -> None:
        bus_num = self.config.connection.bus if self.config.connection.bus is not None else 3
        addr    = self.config.connection.address or 0x29

        while not self._stop_event.is_set():
            try:
                bus    = smbus2.SMBus(bus_num)
                sensor = VL53L1X(bus, addr)
                sensor.init()
                with self._lock:
                    mode = self._mode
                if mode != 3:
                    sensor.set_distance_mode(mode)
                sensor.start_continuous()
                log.info("%s: VL53L1X ready on i2c-%d addr=0x%02X mode=%d",
                         self.id, bus_num, addr, mode)
                self._healthy = True
                self._broadcast_event("mode", self.mode_info())
                self._inner_loop(sensor)
            except Exception as exc:
                self._healthy = False
                log.warning("%s: sensor error — %s — retrying in 3s", self.id, exc)
                self._stop_event.wait(3)

        self._healthy = False

    def _inner_loop(self, sensor: VL53L1X) -> None:
        while not self._stop_event.is_set():
            # Apply a staged manual mode change — hardware is touched only here.
            with self._lock:
                pending = self._pending_mode
                self._pending_mode = None
                auto = self._auto
            if pending is not None and pending != self._mode:
                sensor.set_distance_mode(pending)
                self._mode = pending
                self._broadcast_event("mode", self.mode_info())

            mm = sensor.read_mm(timeout=0.2)

            # Auto-ranging: at most one step per reading, hysteresis-gated.
            if auto and mm is not None:
                new = self._auto_step(self._mode, mm)
                if new != self._mode:
                    sensor.set_distance_mode(new)
                    self._mode = new
                    self._broadcast_event("mode", self.mode_info())

            reading = SensorReading(
                sensor_id=self.id,
                sensor_type="vl53l1x",
                timestamp=time.time(),
                data={
                    "distance_mm": mm,
                    "strength":    None,
                    "temp_c":      None,
                },
            )
            self._broadcast(reading)
