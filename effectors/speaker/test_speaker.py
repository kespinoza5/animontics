"""Unit tests for the speaker effector — SD gate + stream accounting (no hardware)."""
from __future__ import annotations

from core.effector_base import create_effector
from core.models import EffectorConfig
from effectors.speaker.effector import Speaker


class FakeLine:
    def __init__(self):
        self.values = []
    def set(self, value):
        self.values.append(bool(value))
    def close(self):
        pass


def _speaker():
    cfg = EffectorConfig(id="voice", type="speaker",
                         params={"alsa_device": "hw:9,9"})
    e = Speaker("voice", cfg)
    e.attach_devices({})
    e._sd = FakeLine()                              # swap the (Null) line for a spy
    return e


def test_sd_gate_request_lane():
    e = _speaker()
    e.start()
    assert e._sd.values == [True]                   # amp enabled by default
    assert e.handle_request({"on": False}) == {"set": {"on": False}}
    assert e._sd.values[-1] is False
    assert e.state()["on"] is False
    assert "error" in e.handle_request({})


def test_stream_counts_even_without_player():
    e = _speaker()                                  # hw:9,9 / no aplay on dev box
    e.feed(b"\x00\x01" * 512)
    e.feed(b"\x00\x01" * 512)
    s = e.state()
    assert s["bytes_fed"] == 2048
    assert s["playing"] is False                    # gracefully unplayed
    e.stop()


def test_descriptor_and_lanes():
    e = _speaker()
    d = e.descriptor()
    assert set(d["lanes"]) == {"request", "stream"}
    assert d["format"]["rate"] == 48000 and d["format"]["channels"] == 2


def test_registry():
    assert isinstance(create_effector(EffectorConfig(id="v", type="speaker")), Speaker)
