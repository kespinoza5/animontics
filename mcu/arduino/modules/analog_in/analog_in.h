#pragma once
#include <Arduino.h>

// Reads a fixed set of ADC pins into a slice of the uplink frame.
// Hardware I/O only — no framing, no calibration (the node owns meaning).
//
// Optional, renesas-only (RA4M1) knobs — no-ops on AVR:
//   - aref = AREF_EXTERNAL → analogReference(AR_EXTERNAL): use the voltage on the
//     AREF pin as full-scale. Tie AREF to 5 V for ratiometric sensors (MB1010 AN,
//     ACS712) so supply variation cancels in the node-side calibration.
//   - adc_bits > 0 → analogReadResolution(adc_bits). 0 leaves the core default
//     (10-bit, 0..1023) — what the bench calibration is taken against.
class AnalogIn {
public:
  enum Aref : uint8_t { AREF_DEFAULT = 0, AREF_EXTERNAL = 1 };

  AnalogIn(const uint8_t *pins, uint8_t count,
           uint8_t aref = AREF_DEFAULT, uint8_t adc_bits = 0)
      : _pins(pins), _count(count), _aref(aref), _adc_bits(adc_bits) {}
  void setup();
  void read(int16_t *out) const;   // writes _count signed samples into out[0.._count-1]

private:
  const uint8_t *_pins;
  uint8_t _count;
  uint8_t _aref;
  uint8_t _adc_bits;
};
