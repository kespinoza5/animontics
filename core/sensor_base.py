from __future__ import annotations

import json
import queue
from abc import ABC, abstractmethod
from typing import Any

from core.broadcaster import Broadcaster
from core.models import SensorConfig, SensorReading


class SensorBase(ABC):
    """
    Abstract base class for all sensor plugins.

    Subclasses implement the hardware-specific start/stop/read loop.
    Broadcasting to HTTP clients is handled here via Broadcaster — subclasses
    call self._broadcast(reading) after each successful reading.
    """

    def __init__(self, sensor_id: str, config: SensorConfig) -> None:
        self.id = sensor_id
        self.config = config
        self._broadcaster = Broadcaster()
        self._latest: SensorReading | None = None

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def start(self) -> None:
        """Open hardware connection and start the background reading thread."""

    @abstractmethod
    def stop(self) -> None:
        """Signal the reading thread to stop and release hardware resources."""

    @property
    @abstractmethod
    def latest(self) -> SensorReading | None:
        """Most recent reading, or None if no reading has been taken yet."""

    @abstractmethod
    def is_healthy(self) -> bool:
        """True if the sensor is connected and producing readings."""

    # ── Provided — subclasses do not need to override these ──────────────────

    def subscribe(self) -> queue.Queue[str]:
        """Register a new subscriber. Returns a queue that receives JSON payloads."""
        return self._broadcaster.subscribe()

    def unsubscribe(self, q: queue.Queue[str]) -> None:
        self._broadcaster.unsubscribe(q)

    def _broadcast(self, reading: SensorReading) -> None:
        """Store latest and push JSON to all subscribers. Called by subclass threads."""
        self._latest = reading
        self._broadcaster.broadcast(reading.to_sse())

    def _broadcast_event(self, event: str, data: dict[str, Any]) -> None:
        """
        Push a *named* SSE event to all subscribers (control/state changes such
        as a range-mode switch), separate from the default reading stream.

        Clients receive it as an addressable SSE event (EventSource
        addEventListener(event, …)); the default onmessage reading handler is
        unaffected. Called by subclass threads.
        """
        self._broadcaster.broadcast(f"event: {event}\ndata: {json.dumps(data)}\n\n")
