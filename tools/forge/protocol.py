"""forge's view of the MCU↔node link codec.

The implementation lives in core.mcu_link (the node decodes with it at runtime,
and core/ — unlike tools/ — is deployed to boards). forge re-exports it here so
the composer/firmware side has a natural `tools.forge.protocol` handle and so the
authoritative spec has one home.
"""
from __future__ import annotations

from core.mcu_link import (  # noqa: F401
    CMD_SET_DUTY,
    CMD_SET_GPIO,
    CMD_SET_US,
    MAGIC,
    MAX_CHANNELS,
    VERSION,
    Command,
    Frame,
    FrameStream,
    decode,
    decode_command,
    encode,
    encode_command,
    frame_size,
)
