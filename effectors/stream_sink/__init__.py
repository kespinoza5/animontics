try:
    from effectors.stream_sink.effector import StreamSink
except ImportError:
    pass  # METADATA below must still load

METADATA = {
    "type": "stream_sink",
    "description": "Reference stream-lane sink — counts bytes fed (testing).",
    "params": [],
}

__all__ = ["StreamSink", "METADATA"]
