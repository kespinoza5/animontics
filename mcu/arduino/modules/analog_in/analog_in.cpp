#include "analog_in.h"

void AnalogIn::setup() {
#if defined(ARDUINO_ARCH_RENESAS)
  if (_aref == AREF_EXTERNAL) {
    analogReference(AR_EXTERNAL);     // AREF pin = full-scale (tie to 5 V)
  }
  if (_adc_bits) {
    analogReadResolution(_adc_bits);  // 0 leaves the 10-bit default
  }
#else
  (void)_aref;
  (void)_adc_bits;                    // AVR: fixed 10-bit, no AREF-external knob here
#endif
  for (uint8_t i = 0; i < _count; ++i) {
    pinMode(_pins[i], INPUT);
  }
}

void AnalogIn::read(int16_t *out) const {
  for (uint8_t i = 0; i < _count; ++i) {
    out[i] = (int16_t)analogRead(_pins[i]);   // default 10-bit (0..1023)
  }
}
