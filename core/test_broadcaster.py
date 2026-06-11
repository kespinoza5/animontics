"""Unit tests for the pub/sub broadcasters — delivery and backpressure policy.

The two classes differ deliberately: Broadcaster DROPS a slow client (scalar
readings — a stalled consumer is dead weight), FrameBroadcaster KEEPS the
client but discards stale frames (latest-wins for image-like streams).
"""
from __future__ import annotations

from core.broadcaster import Broadcaster, FrameBroadcaster


# ── Broadcaster (text/SSE lane) ───────────────────────────────────────────────

def test_broadcast_delivers_to_all_subscribers():
    b = Broadcaster()
    q1, q2 = b.subscribe(), b.subscribe()
    b.broadcast("payload")
    assert q1.get_nowait() == "payload"
    assert q2.get_nowait() == "payload"


def test_unsubscribe_stops_delivery_and_is_idempotent():
    b = Broadcaster()
    q = b.subscribe()
    b.unsubscribe(q)
    b.unsubscribe(q)            # second call must not raise
    b.broadcast("x")
    assert q.empty()
    assert b.subscriber_count == 0


def test_slow_client_is_pruned_on_overflow():
    b = Broadcaster(maxsize=2)
    slow = b.subscribe()        # never drains
    live = b.subscribe()        # drains after every broadcast
    b.broadcast("0"); live.get_nowait()
    b.broadcast("1"); live.get_nowait()
    b.broadcast("2"); live.get_nowait()   # slow's queue was full → slow pruned
    assert b.subscriber_count == 1
    b.broadcast("3")
    assert slow.qsize() == 2              # no new delivery to the pruned client
    assert live.get_nowait() == "3"       # live client unaffected


# ── FrameBroadcaster (binary frame lane) ──────────────────────────────────────

def test_frames_latest_wins_keeps_client_connected():
    fb = FrameBroadcaster(maxsize=2)
    q = fb.subscribe()
    for i in range(5):
        fb.broadcast(bytes([i]))
    # Client is still subscribed (NOT pruned like the text lane) …
    assert fb.subscriber_count == 1
    # … and holds only the freshest frames.
    assert q.qsize() == 2
    frames = [q.get_nowait(), q.get_nowait()]
    assert frames[-1] == bytes([4])     # newest frame always present


def test_frames_unsubscribe_idempotent():
    fb = FrameBroadcaster()
    q = fb.subscribe()
    fb.unsubscribe(q)
    fb.unsubscribe(q)
    fb.broadcast(b"x")
    assert q.empty()
