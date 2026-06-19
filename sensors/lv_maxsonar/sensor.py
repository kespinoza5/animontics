from __future__ import annotations

import logging
import threading
import time

import serial

from core.analog_array import AnalogArrayBase
from core.models import SensorConfig, SensorReading
from core.registry import register
from core.sensor_base import SensorBase
from sensors.lv_maxsonar.driver import parse_line

log = logging.getLogger(__name__)

# Exact conversion (1 inch = 25.4 mm). NOTE: the MB1010 reports range as *whole
# inches*, so distance_mm is quantized to ~25 mm steps — that's the sensor's
# output resolution, not a precision figure.
INCHES_TO_MM = 25.4


@register("lv_maxsonar")
class LVMaxSonar:
    r"""Dispatcher — the MB1010 reaches the node two ways (picked by config shape).

    ``create()`` calls ``LVMaxSonar(id, config)``; ``__new__`` returns the right
    concrete sensor (so ``__init__`` is never re-run on it):

    - **Direct UART** (``connection:`` set): the SBC reads ``R<NNN>\r`` itself
      (needs a hardware inverter on TX — the MB1010 line is inverted RS232 logic).
      → :class:`LVMaxSonarSensor`.
    - **Device-fed** (``devices:``/``channels:`` set): an MCU (e.g. the LR4Z RA4M1)
      reads the sonar and streams a value per channel — inches (digital lane) or
      raw ADC counts (analog AN lane). → :class:`LVMaxSonarArray`.
    """

    def __new__(cls, sensor_id: str, config: SensorConfig):
        if config.connection is not None:
            return LVMaxSonarSensor(sensor_id, config)
        return LVMaxSonarArray(sensor_id, config)


class LVMaxSonarArray(AnalogArrayBase):
    """Device-fed MB1010: distance from an MCU stream, one value per channel.

    Each channel's ``calibration`` is ``{type: maxsonar, mode: inches|counts, ...}``:

      - ``mode: inches`` — the channel value already *is* range in inches (the
        firmware ``serial_sonar`` module parsed ``R<NNN>``); ``distance_mm =
        round(inches * 25.4)``. A value < 0 is the "no reading yet" sentinel and
        is skipped. Output is quantized to ~25 mm (whole-inch source resolution).
      - ``mode: counts`` — the channel value is raw ADC counts off the AN pin;
        ``distance_mm = round(counts * scale)``. ``scale`` (mm per count) is
        bench-set and absorbs the ADC reference, so it's correct with or without
        AREF=5 V.

    Raw counts are always emitted (by the base); enrich adds ``distance_mm`` for
    the maxsonar channel(s).
    """

    sensor_type = "lv_maxsonar"

    def enrich(self, data: dict, raw: dict[str, int]) -> None:
        # distance_mm is scalar (each instance carries one sonar lane), so stop at
        # the first maxsonar channel rather than letting a second clobber it.
        for ch in self.config.channels:
            cal = ch.calibration or {}
            if cal.get("type") != "maxsonar" or ch.signal not in raw:
                continue
            value = raw[ch.signal]
            mode = cal.get("mode", "inches")
            if mode == "inches":
                if value is None or value < 0:
                    continue                       # -1 = no frame parsed yet
                mm = round(value * INCHES_TO_MM)   # whole-inch source → ~25 mm steps
            else:  # counts (analog AN lane)
                mm = round(value * float(cal.get("scale", 0.0)))
            data["distance_mm"] = mm
            data.setdefault("strength", None)
            data.setdefault("temp_c", None)
            break


class LVMaxSonarSensor(SensorBase):
    r"""MaxBotix LV-MaxSonar-EZ ultrasonic distance sensor over UART (direct).

    Config connection fields:
      type:      uart
      port:      /dev/ttyS0
      baud_rate: 9600

    The MB1010 TX is inverted (RS232-format, idles LOW); reading it directly on an
    SBC UART needs a hardware inverter (74HC14 / 2N3904) on the TX line. See README.
    """

    BAUD_DEFAULT = 9_600

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        super().__init__(sensor_id, config)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._healthy = False

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop, daemon=True, name=f"sensor-{self.id}"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return self._healthy

    # ── Background reading loop ───────────────────────────────────────────────

    def _read_loop(self) -> None:
        port      = self.config.connection.port or "/dev/ttyS0"
        baud_rate = self.config.connection.baud_rate or self.BAUD_DEFAULT

        while not self._stop_event.is_set():
            try:
                with serial.Serial(port, baud_rate, timeout=2) as ser:
                    log.info("%s: opened %s at %d baud", self.id, port, baud_rate)
                    self._healthy = True
                    self._inner_loop(ser)
            except serial.SerialException as exc:
                self._healthy = False
                log.warning("%s: serial error — %s — retrying in 2s", self.id, exc)
                self._stop_event.wait(2)

        self._healthy = False

    def _inner_loop(self, ser: serial.Serial) -> None:
        while not self._stop_event.is_set():
            raw = ser.read_until(b"\r")
            if not raw:
                continue
            inches = parse_line(raw)
            if inches is None:
                continue
            distance_mm = round(inches * INCHES_TO_MM)
            reading = SensorReading(
                sensor_id=self.id,
                sensor_type="lv_maxsonar",
                timestamp=time.time(),
                data={
                    "distance_mm": distance_mm,
                    "strength":    None,
                    "temp_c":      None,
                },
            )
            self._broadcast(reading)
