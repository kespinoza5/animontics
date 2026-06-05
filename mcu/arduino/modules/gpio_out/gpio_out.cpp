#include "gpio_out.h"

void GpioOut::setup() {
  for (uint8_t i = 0; i < _count; ++i) {
    pinMode(_pins[i], OUTPUT);
    digitalWrite(_pins[i], LOW);
  }
}

void GpioOut::tick(unsigned long now) {
  if (_blink_ms == 0) {
    return;
  }
  if (now - _last >= _blink_ms) {
    _last = now;
    _state = !_state;
    for (uint8_t i = 0; i < _count; ++i) {
      digitalWrite(_pins[i], _state ? HIGH : LOW);
    }
  }
}
