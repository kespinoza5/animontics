"""Shared pub/sub broadcast utility used by all sensor plugins."""
from __future__ import annotations

import queue
import threading
from typing import Any


class Broadcaster:
    """
    Queue-per-subscriber pub/sub utility.

    Replaces the _clients / _clients_lock pattern duplicated across all sensor
    servers. SSE and WebSocket route handlers subscribe a queue when a client
    connects; the sensor's background thread calls broadcast() after each
    reading. Stale queues from disconnected clients are pruned automatically.
    """

    def __init__(self, maxsize: int = 10) -> None:
        self._clients: list[queue.Queue[str]] = []
        self._lock = threading.Lock()
        self._maxsize = maxsize

    def subscribe(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue(maxsize=self._maxsize)
        with self._lock:
            self._clients.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[str]) -> None:
        with self._lock:
            try:
                self._clients.remove(q)
            except ValueError:
                pass

    def broadcast(self, payload: str) -> None:
        stale: list[queue.Queue[str]] = []
        with self._lock:
            for q in self._clients:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    stale.append(q)
            for q in stale:
                self._clients.remove(q)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._clients)
