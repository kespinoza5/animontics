"""ALSA capture + PCM block math for audio_in. Hardware I/O only — no threading,
no HTTP. The DSP helpers are pure and unit-tested on any platform.

Capture backends, tried in order:
  1. pyalsaaudio (`alsaaudio`) — in-process, lowest overhead.
  2. `arecord` subprocess piping raw S16_LE — present on every ALSA board.
Both deliver interleaved signed 16-bit little-endian blocks.
"""
from __future__ import annotations

import array
import math
import subprocess
import sys

_LITTLE_ENDIAN = sys.byteorder == "little"
FULL_SCALE = 32768.0


def block_stats(pcm: bytes, channels: int) -> list[dict[str, float]]:
    """Per-channel RMS + peak of one interleaved S16_LE block, as 0..1 of FS.

    Pure function (the unit-tested meaning layer). Returns one
    {"rms": …, "peak": …, "dbfs": …} per channel; silence → dbfs -120.
    """
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % (2 * channels))])
    if not _LITTLE_ENDIAN:
        samples.byteswap()
    n = len(samples) // channels
    out = []
    for ch in range(channels):
        acc = 0
        peak = 0
        for i in range(ch, len(samples), channels):
            v = samples[i]
            acc += v * v
            peak = max(peak, abs(v))
        rms = math.sqrt(acc / n) / FULL_SCALE if n else 0.0
        out.append({
            "rms": round(rms, 5),
            "peak": round(peak / FULL_SCALE, 5),
            "dbfs": round(20 * math.log10(rms) if rms > 0 else -120.0, 1),
        })
    return out


class AlsaCapture:
    """One opened capture stream delivering raw S16_LE blocks."""

    def __init__(self, device: str, rate: int, channels: int,
                 block_frames: int) -> None:
        self.device = device
        self.rate = rate
        self.channels = channels
        self.block_frames = block_frames
        self._pcm = None          # pyalsaaudio handle
        self._proc = None         # arecord subprocess
        self._block_bytes = block_frames * channels * 2

    def open(self) -> None:
        try:
            import alsaaudio
            self._pcm = alsaaudio.PCM(
                alsaaudio.PCM_CAPTURE, alsaaudio.PCM_NORMAL, device=self.device,
                channels=self.channels, rate=self.rate,
                format=alsaaudio.PCM_FORMAT_S16_LE, periodsize=self.block_frames,
            )
            return
        except ImportError:
            pass                                   # fall through to arecord
        self._proc = subprocess.Popen(
            ["arecord", "-D", self.device, "-f", "S16_LE", "-r", str(self.rate),
             "-c", str(self.channels), "-t", "raw", "-q"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )

    def read(self) -> bytes:
        """Block until one block is available; b'' on stream end."""
        if self._pcm is not None:
            length, data = self._pcm.read()
            return data if length > 0 else b""
        if self._proc is not None and self._proc.stdout is not None:
            return self._proc.stdout.read(self._block_bytes) or b""
        return b""

    def close(self) -> None:
        if self._pcm is not None:
            try:
                self._pcm.close()
            except Exception:
                pass
            self._pcm = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                pass
            self._proc = None
