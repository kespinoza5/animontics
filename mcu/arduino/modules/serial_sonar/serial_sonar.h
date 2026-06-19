#pragma once
#include <Arduino.h>

// Reads a MaxBotix LV-MaxSonar ASCII range frame off a hardware UART.
//
// The MB1010 TX is inverted (RS232-format, idles LOW); a hardware 2N3904 inverter
// ahead of the UART RX pin restores normal TTL polarity, so this reads clean
// `R<NNN>\r` frames (NNN = range in inches, 0..255). Hardware I/O only — the
// inches→mm meaning lives node-side in the lv_maxsonar sensor.
//
// poll() drains + parses bytes every loop; read() emits the latest range as one
// frame channel (-1 until the first valid frame).
class SerialSonar {
public:
  explicit SerialSonar(HardwareSerial &port)
      : _port(port), _idx(0), _latest(-1) {}
  void begin(unsigned long baud) { _port.begin(baud); }
  void poll();                              // drain + parse R<NNN>\r → _latest (inches)
  void read(int16_t *out) const { out[0] = _latest; }

private:
  HardwareSerial &_port;
  char _buf[8];
  uint8_t _idx;
  int16_t _latest;                          // last good inches; -1 until first frame
};
