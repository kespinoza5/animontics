"""Unit tests for the stream_sink effector — stream lane (no hardware)."""
from __future__ import annotations

from core.effector_base import create_effector
from core.models import EffectorConfig
from effectors.stream_sink.effector import StreamSink  # noqa: F401  (registers the type)


def test_stream_sink_accumulates():
    e = create_effector(EffectorConfig(id="spk", type="stream_sink"))
    e.feed(b"abcd")
    e.feed(b"xy")
    assert e.state() == {"bytes_received": 6, "last_chunk": 2}
    assert e.lanes == ("stream",)
