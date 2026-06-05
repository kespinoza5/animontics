#pragma once
#include <Arduino.h>

// Uplink framing — protocol v1.
//
// The on-wire layout MUST stay identical to core/mcu_link.py (that file is the
// authoritative spec; the node decodes with it). If you change one, bump
// PROTOCOL_VERSION in both.
//
//   magic 'A''M' | version | seq | count | int16[count] LE | checksum(uint8)
class TransportSerial {
public:
  static const uint8_t PROTOCOL_VERSION = 1;

  void begin(unsigned long baud) { Serial.begin(baud); }
  void send(const int16_t *frame, uint8_t count, uint8_t seq) const;
};
