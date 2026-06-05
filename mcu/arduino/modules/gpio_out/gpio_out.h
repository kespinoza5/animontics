#pragma once
#include <Arduino.h>

// Digital outputs with an optional non-blocking heartbeat blink. Proves that the
// composer can fold a module with its own loop() work into the main loop.
class GpioOut {
public:
  GpioOut(const uint8_t *pins, uint8_t count, unsigned long blink_ms)
      : _pins(pins), _count(count), _blink_ms(blink_ms), _last(0), _state(false) {}
  void setup();
  void tick(unsigned long now);

private:
  const uint8_t *_pins;
  uint8_t _count;
  unsigned long _blink_ms;
  unsigned long _last;
  bool _state;
};
