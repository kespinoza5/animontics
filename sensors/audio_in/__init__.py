try:
    from sensors.audio_in.sensor import AudioIn
except ImportError:
    pass  # capture backends are Linux-only; package stays importable

#: Audition — stereo capture from the PCM1808 on the shared-clock I2S bus.
#: Connectionless: the I2S bus is OS plumbing (overlay), not fleet wiring.
METADATA = {
    "type": "audio_in",
    "name": "Audio capture (I2S stereo ADC)",
    "description": "Stereo audio from an I2S capture device (PCM1808, master-mode "
                   "on the SI5351 clock tree). Raw blocks on the binary frame "
                   "lane; rate-limited level summaries on the JSON lane.",
    "connection": {
        "supported": [],          # connectionless; ALSA device in params
        "defaults": {},
        "valid": {},
    },
    "data_keys": {
        "frame_id": "int — id of the newest binary frame at summary time",
        "rate": "int — sample rate in Hz",
        "channels": "dict[str,dict] — per channel {rms, peak} (0..1 FS) + dbfs; "
                    "the raw audio rides /sensors/<id>/frames "
                    "(header <IHHI> = frame_id, channels, bits, rate + S16_LE)",
    },
}

__all__ = ["AudioIn", "METADATA"]
