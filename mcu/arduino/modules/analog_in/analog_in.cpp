#include "analog_in.h"

void AnalogIn::setup() {
  for (uint8_t i = 0; i < _count; ++i) {
    pinMode(_pins[i], INPUT);
  }
}

void AnalogIn::read(int16_t *out) const {
  for (uint8_t i = 0; i < _count; ++i) {
    out[i] = (int16_t)analogRead(_pins[i]);   // 0..1023 on the ATmega328P
  }
}
