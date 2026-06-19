#pragma once
#include <Arduino.h>

// Fan tach (FG) RPM via pin-change interrupts. Hardware I/O only — counts edges
// and converts to RPM; no framing, no calibration (the node owns meaning).
//
// FG is open-collector (4-pin fans keep it valid at any PWM duty), so each pin is
// driven INPUT_PULLUP and falling edges are counted. RPM is computed per read()
// from the edge count and the elapsed time since the previous read.
//
// Interrupt slots are a fixed module-global bank (TACH_MAX total channels across
// all tach instances), since attachInterrupt() takes a bare function pointer.
class Tach {
public:
  static const uint8_t TACH_MAX = 6;

  Tach(const uint8_t *pins, uint8_t count, uint16_t pulses_per_rev)
      : _pins(pins), _count(count), _ppr(pulses_per_rev ? pulses_per_rev : 1),
        _last_ms(0) {}
  void setup();
  void read(int16_t *out, unsigned long now);   // writes _count RPM samples

private:
  const uint8_t *_pins;
  uint8_t _count;
  uint16_t _ppr;
  uint8_t _slot[TACH_MAX];     // interrupt-bank slot per configured pin
  unsigned long _last_ms;
};
