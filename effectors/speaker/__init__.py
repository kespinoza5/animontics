try:
    from effectors.speaker.effector import Speaker
except ImportError:
    pass  # ALSA/hardware deps unavailable — METADATA below must still load

METADATA = {
    "type": "speaker",
    "description": "ALSA speaker — request-lane control + stream-lane PCM audio.",
    "params": ["alsa_device", "sample_rate", "channels", "sd_line"],
}

__all__ = ["Speaker", "METADATA"]
