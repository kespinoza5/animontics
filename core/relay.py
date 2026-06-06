"""The thalamic relay — an in-process named-signal bus (this cortex's thalamus).

Producers (sensors, models, policies) publish latest values under dotted names
(`gas_array.raw.mq135`, `board_temp.cpu_c`); consumers (policies) read them to
build observations. A gating hook can filter/scale on publish (attention).

Today it is local and in-process. The same interface is the seam for the
brain-inspired substrate to come: cross-node delivery, and declared reciprocal
predict-down / error-up tracts between cortices.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class Relay:
    """Latest-value pub/sub keyed by dotted signal name, with an optional gate."""

    def __init__(self, gate: Callable[[str, Any], Any] | None = None) -> None:
        # gate(name, value) -> value to store, or None to drop (attention/gating).
        self._gate = gate
        self._values: dict[str, Any] = {}
        self._lock = threading.Lock()

    def publish(self, name: str, value: Any) -> None:
        if self._gate is not None:
            value = self._gate(name, value)
            if value is None:
                return
        with self._lock:
            self._values[name] = value

    def publish_tree(self, prefix: str, data: dict) -> None:
        """Flatten a nested reading dict into dotted signal names and publish each."""
        for key, value in data.items():
            name = f"{prefix}.{key}"
            if isinstance(value, dict):
                self.publish_tree(name, value)
            else:
                self.publish(name, value)

    def latest(self, name: str, default: Any = None) -> Any:
        with self._lock:
            return self._values.get(name, default)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._values)
