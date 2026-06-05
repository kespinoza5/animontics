#pragma once
#include <Arduino.h>

// Reads a fixed set of ADC pins into a slice of the uplink frame.
// Hardware I/O only — no framing, no calibration (the node owns meaning).
class AnalogIn {
public:
  AnalogIn(const uint8_t *pins, uint8_t count) : _pins(pins), _count(count) {}
  void setup();
  void read(int16_t *out) const;   // writes _count signed samples into out[0.._count-1]

private:
  const uint8_t *_pins;
  uint8_t _count;
};
