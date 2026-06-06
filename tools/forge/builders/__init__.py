"""Builder implementations, imported here so their @register_builder calls fire.

forge.py imports this package once; each concrete builder registers under its
target key. Add new targets (fpga, accel) by importing them here — nothing else
in forge needs to change.
"""
from __future__ import annotations

from tools.forge.builders import arduino  # noqa: F401  (registers "mcu.arduino")
from tools.forge.builders import circuit_python  # noqa: F401  (registers "mcu.circuit_python")
