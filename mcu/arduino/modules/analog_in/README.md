# analog_in (arduino module)

Samples a fixed set of ADC pins into the uplink frame. **role:** sensor ·
**claims:** adc pins · **provides:** one channel per configured pin (signed
int16 counts).

- `analog_in.h/.cpp` — `AnalogIn::read()` does `analogRead` per pin into the frame slice.
- `decl/setup/read.j2` — instance, `pinMode`, and `read(g_frame + offset)` composed into `main.ino`.

No calibration here — the node's `mq_array`/`pressure_array` sensor owns meaning.
