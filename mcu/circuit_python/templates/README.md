# mcu/circuit_python/templates/

The generic CircuitPython runtime that `forge` fills.

- `code.py.j2` — one fixed runtime for every CircuitPython board. The composer
  renders it with the instance's ADS1115 chips baked in (`_adcs`, the ordered
  `CHANNELS` list, sample period) → `firmware/<id>/code.py`. At runtime it scans
  the channels each tick and writes protocol-v1 frames (mirroring
  `core/mcu_link.py`) over USB serial. No compile step — deploy copies it to
  the board's `CIRCUITPY` drive.
