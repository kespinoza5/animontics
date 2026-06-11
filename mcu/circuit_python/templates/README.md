# mcu/circuit_python/templates/

The generic CircuitPython runtime that `forge` fills.

- `code.py.j2` — one fixed runtime for every CircuitPython board. The composer
  renders it with the instance's module configuration baked in: an ordered
  `FRAME_SOURCES` list (ADS1115 reads, native ADC pins, tach RPM, matrix-scan row
  tags) for the afferent lane, and a command dispatch block (PWM duty, servo µs,
  GPIO level) for the efferent lane — both conditional on which modules the
  contract includes. At runtime it scans sources each tick and writes
  `core/mcu_link.py` protocol-v1 frames over USB serial. No compile step —
  deploy copies it to the board's `CIRCUITPY` drive.
