#include "transport_serial.h"

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
