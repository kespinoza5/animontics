#include "pwm_out.h"

void PwmOut::setup() {
  for (uint8_t i = 0; i < _count; ++i) {
    pinMode(_pins[i], OUTPUT);
    analogWrite(_pins[i], 0);
  }
}

void PwmOut::set_duty(uint8_t idx, uint8_t duty) {
  if (idx < _count) {
    analogWrite(_pins[idx], duty);
  }
}
