"""AnalogArrayBase — base for sensors that read a flat vector of analog channels
streamed from one or more devices.

An array sensor is decoupled from the hardware that feeds it: a Device (an MCU
link, see core/device.py) owns the transport and pushes decoded frames; this base
subscribes, keeps the latest samples per device, and composes one reading by
mapping each configured channel `(device, index) → signal + calibration`. A
sensor may span several devices — the cranial-pressure surface is one logical
`pressure_array` over 4 MCUs. `mq_array` is the single-device case.

Raw counts are ALWAYS emitted; subclasses add calibrated/derived values via
`enrich()`. The base owns no transport (that's the device) — the firmware↔Python
boundary: devices move bytes, the sensor adds meaning.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from core.models import SensorReading
from core.sensor_base import SensorBase

if TYPE_CHECKING:
    from core.device import Device
    from core.mcu_link import Frame

log = logging.getLogger(__name__)


class AnalogArrayBase(SensorBase):
    """Base for device-fed analog array sensors. Subclasses set `sensor_type` and
    may override `enrich()`."""

    sensor_type: str = "analog_array"

    def __init__(self, sensor_id, config) -> None:
        super().__init__(sensor_id, config)
        self._devices: dict[str, "Device"] = {}
        self._samples: dict[str, tuple[int, ...]] = {}   # device id → latest samples
        self._lock = threading.Lock()

    # ── Device binding (app.py calls attach_devices before start) ──────────────

    @property
    def device_ids(self) -> set[str]:
        """Device ids referenced by this sensor's channels."""
        return {ch.device for ch in self.config.channels if ch.device}

    def attach_devices(self, devices: dict[str, "Device"]) -> None:
        missing = self.device_ids - set(devices)
        if missing:
            raise ValueError(f"sensor '{self.id}': unknown device(s) {sorted(missing)}")
        self._devices = {d: devices[d] for d in self.device_ids}

    # ── SensorBase contract ───────────────────────────────────────────────────

    def start(self) -> None:
        for dev_id, dev in self._devices.items():
            dev.subscribe(lambda frame, _id=dev_id: self.ingest(_id, frame))

    def stop(self) -> None:
        pass  # the device owns the read thread; nothing to join here

    @property
    def latest(self) -> SensorReading | None:
        return self._latest

    def is_healthy(self) -> bool:
        return any(d.is_healthy() for d in self._devices.values())

    # ── Ingest + compose ──────────────────────────────────────────────────────

    def ingest(self, device_id: str, frame: "Frame") -> SensorReading:
        """Record a device's latest samples, compose + broadcast a reading.

        Called from the device read thread (and directly in tests). Returns the
        composed reading.
        """
        with self._lock:
            self._samples[device_id] = frame.samples
        reading = self._compose(frame.seq)
        self._broadcast(reading)
        return reading

    def _compose(self, seq: int) -> SensorReading:
        raw: dict[str, int] = {}
        with self._lock:
            for ch in self.config.channels:
                samples = self._samples.get(ch.device)
                if samples and 0 <= ch.index < len(samples):
                    raw[ch.signal] = int(samples[ch.index])
        data: dict = {"seq": seq, "raw": raw}
        self.enrich(data, raw)
        return SensorReading(
            sensor_id=self.id,
            sensor_type=self.sensor_type,
            timestamp=time.time(),
            data=data,
        )

    # ── Overridable interpretation hook ───────────────────────────────────────

    def enrich(self, data: dict, raw: dict[str, int]) -> None:
        """Add calibrated/derived values to `data`. Default: raw only."""
