#pragma once
#include <Arduino.h>

// Inbound command dispatch: handler(cmd_id, args, nargs).
typedef void (*CommandHandler)(uint8_t cmd, const int16_t *args, uint8_t n);

// Uplink framing — protocol v1, plus inbound command frames.
//
// The on-wire layout MUST stay identical to core/mcu_link.py (that file is the
// authoritative spec; the node decodes with it). If you change one, bump
// PROTOCOL_VERSION in both.
//
//   uplink  (MCU→node):  'A''M' | version | seq | count | int16[count] | checksum
//   command (node→MCU):  'A''C' | version | cmd  | nargs | int16[nargs] | checksum
class TransportSerial {
public:
  static const uint8_t PROTOCOL_VERSION = 1;
  static const uint8_t MAX_ARGS = 8;

  void begin(unsigned long baud) { Serial.begin(baud); }
  void send(const int16_t *frame, uint8_t count, uint8_t seq) const;
  void poll(CommandHandler handler);   // drain inbound 'AC' command frames

private:
  static const uint8_t RX_CAP = 5 + 2 * MAX_ARGS + 1;   // largest command frame
  uint8_t _rx[RX_CAP];
  uint8_t _rxlen = 0;
};
