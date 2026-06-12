from __future__ import annotations

from typing import TYPE_CHECKING

from core.effector_base import EffectorBase, register_effector

if TYPE_CHECKING:
    from core.models import EffectorConfig


@register_effector("stream_sink")
class StreamSink(EffectorBase):
    """Reference stream-lane effector (no hardware) — records what it receives.

    Proves the continuous-flow lane end to end (WS /effectors/{id}/stream → feed)
    and is the template a real speaker / addressable-LED-strip effector follows.
    """

    effector_type = "stream_sink"
    lanes = ("stream",)
    SPEC = {
        "description": "Reference stream-lane sink — counts bytes fed (testing).",
        "params": [],
    }

    def __init__(self, effector_id: str, config: "EffectorConfig") -> None:
        super().__init__(effector_id, config)
        self._bytes = 0
        self._last_len = 0

    def feed(self, chunk: bytes) -> None:
        self._bytes += len(chunk)
        self._last_len = len(chunk)

    def state(self) -> dict:
        return {"bytes_received": self._bytes, "last_chunk": self._last_len}
