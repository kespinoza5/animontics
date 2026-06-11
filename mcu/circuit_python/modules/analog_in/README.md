# analog_in (circuit_python module)

Sample the board's **own ADC pins** via `analogio.AnalogIn` into uplink frame
channels — one per configured pin, in pin order. **role:** sensor ·
**provides:** `channels: per_pin`.

The frame lane carries signed int16 samples, while CircuitPython's
`AnalogIn.value` is unsigned 0–65535, so the runtime emits **`value >> 1`
(0–32767)** raw counts. The volts mapping (rail, dividers, calibration) is the
node-side sensor's job — firmware moves bytes; Python owns meaning.

Sibling of the `ads1115` module (external I2C ADCs); use both on one board
freely. The AVR family's `analog_in` is the same idea for `analogRead` pins
(10-bit, no shift needed).
