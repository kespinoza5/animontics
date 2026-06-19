# analog_in (arduino module)

Samples a fixed set of ADC pins into the uplink frame. **role:** sensor ·
**claims:** adc pins · **provides:** one channel per configured pin (signed
int16 counts).

- `analog_in.h/.cpp` — `AnalogIn::read()` does `analogRead` per pin into the frame slice.
- `decl/setup/read.j2` — instance, `pinMode`, and `read(g_frame + offset)` composed into `main.ino`.

No calibration here — the node's `mq_array`/`pressure_array`/`current`/`lv_maxsonar`
sensor owns meaning.

**Renesas (RA4M1) options** (config; no-ops on AVR, so the module stays
family-shared):

- `aref: external` → `analogReference(AR_EXTERNAL)` — use the **AREF pin** as
  full-scale. Tie AREF to 5 V for ratiometric sensors (MB1010 AN, ACS712) so
  supply variation cancels in the calibration.
- `adc_bits: <n>` → `analogReadResolution(n)`. Default `0` leaves the core's
  10-bit default (0..1023), which the bench calibration is taken against.
