#include "serial_sonar.h"

#include <stdlib.h>   // atoi

void SerialSonar::poll() {
  while (_port.available() > 0) {
    char c = (char)_port.read();
    if (c == '\r') {                          // end of frame
      _buf[_idx] = '\0';
      if (_idx == 4 && _buf[0] == 'R') {      // "R" + 3 digits
        int v = atoi(_buf + 1);
        if (v >= 0 && v <= 254) {             // MB1010 max range is 254 inches
          _latest = (int16_t)v;
        }
      }
      _idx = 0;
    } else if (_idx < sizeof(_buf) - 1) {
      _buf[_idx++] = c;
    } else {
      _idx = 0;                               // overrun → resync
    }
  }
}
