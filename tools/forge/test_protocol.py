"""Unit tests for the MCU↔node link frame codec (no hardware)."""
from __future__ import annotations

import pytest

from tools.forge import protocol
from tools.forge.protocol import (
    CMD_SET_DUTY,
    Frame,
    FrameStream,
    decode,
    decode_command,
    encode,
    encode_command,
    frame_size,
)


class TestRoundTrip:
    @pytest.mark.parametrize(
        "samples",
        [
            [],
            [0],
            [1023, 0, 512, 255],
            [-32768, -1, 0, 1, 32767],          # full signed int16 range
            list(range(-50, 50)),
        ],
    )
    def test_encode_decode(self, samples):
        frame = decode(encode(samples, seq=7))
        assert frame is not None
        assert frame.seq == 7
        assert list(frame.samples) == samples
        assert frame.version == protocol.VERSION

    def test_frame_size_matches(self):
        for n in (0, 1, 8, 255):
            assert len(encode([0] * n)) == frame_size(n)

    def test_seq_wraps(self):
        assert decode(encode([1], seq=256)).seq == 0
        assert decode(encode([1], seq=257)).seq == 1

    def test_too_many_channels(self):
        with pytest.raises(ValueError):
            encode([0] * 256)


class TestDecodeRejects:
    def test_short(self):
        assert decode(b"") is None
        assert decode(b"AM") is None

    def test_bad_magic(self):
        good = bytearray(encode([1, 2, 3]))
        good[0] = ord("X")
        assert decode(bytes(good)) is None

    def test_bad_version(self):
        good = bytearray(encode([1, 2, 3]))
        good[2] = 0xFF
        assert decode(bytes(good)) is None

    def test_bad_checksum(self):
        good = bytearray(encode([1, 2, 3]))
        good[-1] ^= 0xFF
        assert decode(bytes(good)) is None

    def test_wrong_length(self):
        assert decode(encode([1, 2, 3]) + b"\x00") is None


class TestFrameStream:
    def test_clean_back_to_back(self):
        stream = FrameStream()
        data = encode([1, 2], seq=0) + encode([3, 4], seq=1)
        frames = stream.feed(data)
        assert [f.seq for f in frames] == [0, 1]
        assert [list(f.samples) for f in frames] == [[1, 2], [3, 4]]

    def test_byte_at_a_time(self):
        stream = FrameStream()
        data = encode([10, 20, 30], seq=5)
        got: list[Frame] = []
        for b in data:
            got += stream.feed(bytes([b]))
        assert len(got) == 1
        assert list(got[0].samples) == [10, 20, 30]

    def test_resync_after_garbage(self):
        stream = FrameStream()
        data = b"\x00\xff garbage \x01" + encode([7, 8], seq=2)
        frames = stream.feed(data)
        assert len(frames) == 1
        assert list(frames[0].samples) == [7, 8]

    def test_resync_after_corrupt_frame(self):
        stream = FrameStream()
        corrupt = bytearray(encode([1, 2, 3]))
        corrupt[-1] ^= 0xFF                       # break checksum
        good = encode([4, 5, 6], seq=9)
        frames = stream.feed(bytes(corrupt) + good)
        assert [list(f.samples) for f in frames] == [[4, 5, 6]]
        assert frames[0].seq == 9

    def test_buffer_bounded_on_endless_garbage(self):
        stream = FrameStream(max_buffer=64)
        for _ in range(100):
            stream.feed(b"\x00\x01\x02\x03" * 8)
        assert len(stream._buf) <= 64


class TestCommandCodec:
    def test_round_trip(self):
        cmd = decode_command(encode_command(CMD_SET_DUTY, [2, 200]))
        assert cmd is not None
        assert cmd.cmd_id == CMD_SET_DUTY
        assert list(cmd.args) == [2, 200]

    def test_no_args(self):
        cmd = decode_command(encode_command(9))
        assert cmd is not None and cmd.cmd_id == 9 and cmd.args == ()

    def test_bad_checksum(self):
        b = bytearray(encode_command(CMD_SET_DUTY, [1, 1]))
        b[-1] ^= 0xFF
        assert decode_command(bytes(b)) is None

    def test_command_and_sample_frames_dont_cross_decode(self):
        # distinct magic ('AC' vs 'AM') so neither end mistakes one for the other
        assert decode(encode_command(CMD_SET_DUTY, [1, 2])) is None
        assert decode_command(encode([1, 2], seq=0)) is None
