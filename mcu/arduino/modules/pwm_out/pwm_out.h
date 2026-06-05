#pragma once
#include <Arduino.h>

// PWM outputs. Idle at duty 0 after setup(); set_duty() will be wired to the
// inbound command lane in Phase 5 (fan actuation). Pins are driven, never read.
class PwmOut {
public:
  PwmOut(const uint8_t *pins, uint8_t count) : _pins(pins), _count(count) {}
  void setup();
  void set_duty(uint8_t idx, uint8_t duty);   // 0..255

private:
  const uint8_t *_pins;
  uint8_t _count;
};
