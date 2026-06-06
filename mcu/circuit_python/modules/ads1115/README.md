# ads1115 (circuit_python module)

Reads one or more ADS1115 ADC chips over I2C. **role:** sensor · **provides:**
one frame channel per `(chip, channel)`.

`manifest.yaml` declares `provides: {channels: per_chip_channel}`; the contract
supplies `chips: [{addr, gain, channels: [...]}]`. `forge` flattens these into the
ordered `(addr, channel, gain)` list rendered into `code.py`, which scans them each
tick and streams protocol-v1 frames. No compiled source — the chip list IS the config.
