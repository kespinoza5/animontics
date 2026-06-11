"""Pressure transfer math — pure functions, no I/O."""
from __future__ import annotations


def to_kpa(count: int, scale: float, offset: float = 0.0) -> float:
    """Linear transfer from a raw ADC count to kPa: count * scale + offset.

    `scale`/`offset` come from the transducer datasheet + the ADC reference, per
    channel. (Non-linear transducers can extend this with their own kind.)
    """
    return count * scale + offset
