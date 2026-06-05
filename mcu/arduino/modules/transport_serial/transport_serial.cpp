#include "transport_serial.h"

#include <string.h>   // memmove

void TransportSerial::send(const int16_t *frame, uint8_t count, uint8_t seq) const {
  const uint8_t header[5] = {'A', 'M', PROTOCOL_VERSION, seq, count};
  uint16_t sum = 0;
  for (uint8_t i = 0; i < 5; ++i) {
    sum += header[i];
  }
  Serial.write(header, 5);

  for (uint8_t i = 0; i < count; ++i) {
    const uint8_t lo = (uint8_t)(frame[i] & 0xFF);
    const uint8_t hi = (uint8_t)((frame[i] >> 8) & 0xFF);
    Serial.write(lo);
    Serial.write(hi);
    sum += lo;
    sum += hi;
  }

  Serial.write((uint8_t)(sum & 0xFF));   // checksum: sum of all preceding bytes
}

void TransportSerial::poll(CommandHandler handler) {
  while (Serial.available() > 0) {
    if (_rxlen >= RX_CAP) {                     // full without a valid frame — resync
      memmove(_rx, _rx + 1, --_rxlen);
    }
    _rx[_rxlen++] = (uint8_t)Serial.read();

    for (;;) {
      // Sync to the command magic 'A''C'.
      uint8_t i = 0;
      while (i + 1 < _rxlen && !(_rx[i] == 'A' && _rx[i + 1] == 'C')) {
        i++;
      }
      if (i > 0) {                              // drop everything before the marker
        memmove(_rx, _rx + i, _rxlen - i);
        _rxlen -= i;
      }
      if (_rxlen < 5) {
        break;                                  // need the full header
      }
      const uint8_t n = _rx[4];
      const uint8_t total = 5 + 2 * n + 1;
      if (n > MAX_ARGS || total > RX_CAP) {     // bogus length — step past this magic
        memmove(_rx, _rx + 1, --_rxlen);
        continue;
      }
      if (_rxlen < total) {
        break;                                  // wait for the rest of the frame
      }
      uint16_t sum = 0;
      for (uint8_t k = 0; k < total - 1; ++k) {
        sum += _rx[k];
      }
      if (_rx[2] != PROTOCOL_VERSION || (uint8_t)(sum & 0xFF) != _rx[total - 1]) {
        memmove(_rx, _rx + 1, --_rxlen);        // bad version/checksum — resync
        continue;
      }
      int16_t args[MAX_ARGS];
      for (uint8_t k = 0; k < n; ++k) {
        args[k] = (int16_t)((uint16_t)_rx[5 + 2 * k] | ((uint16_t)_rx[6 + 2 * k] << 8));
      }
      handler(_rx[3], args, n);                 // _rx[3] = cmd_id
      memmove(_rx, _rx + total, _rxlen - total);
      _rxlen -= total;
    }
  }
}
