try:
    from effectors.speaker.effector import Speaker
except ImportError:
    pass  # ALSA/hardware deps unavailable — METADATA below must still load

METADATA = {
    "type": "speaker",
    "description": "ALSA speaker — request-lane control + stream-lane PCM audio.",
    # Playback only: needs the I2S clocks + the Pi's data-OUT line, not data-in.
    "bus": {"kind": "i2s", "roles": ["bclk", "lrck", "dout"]},
    "valid": {"channels": [1, 2],
              "sample_rate": [8000, 16000, 22050, 24000, 32000, 44100, 48000, 96000]},
    "params": ["alsa_device", "sample_rate", "channels", "sd_line"],
}

__all__ = ["Speaker", "METADATA"]
