#pragma once
#include <Arduino.h>

// Digital outputs: an optional non-blocking heartbeat blink (status LED) and/or a
// commandable line driven from the inbound CMD_SET_GPIO lane (e.g. a relay IN).
// A blinking pin (blink_ms > 0) toggles itself; a commanded pin should use
// blink_ms = 0 so set_gpio() owns its level.
class GpioOut {
public:
  GpioOut(const uint8_t *pins, uint8_t count, unsigned long blink_ms)
      : _pins(pins), _count(count), _blink_ms(blink_ms), _last(0), _state(false) {}
  void setup();
  void tick(unsigned long now);
  void set_gpio(uint8_t idx, bool on);   // CMD_SET_GPIO target (node owns active_low)

private:
  const uint8_t *_pins;
  uint8_t _count;
  unsigned long _blink_ms;
  unsigned long _last;
  bool _state;
};
