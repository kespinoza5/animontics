# serial_sonar (arduino module)

Reads a **MaxBotix LV-MaxSonar** ASCII range frame off a hardware UART.
**role:** sensor · **provides:** one frame channel — range in **inches** (signed
int16, `-1` until the first valid frame). **config:** `port` (which hardware
UART; `1` = `Serial1`), `baud` (default 9600), `sample_hz` (default 10).

The MB1010 emits `R<NNN>\r` continuously at ~20 Hz (NNN = inches, 0–255). Its TX
is **inverted** (RS232-format, idles LOW), so a hardware **2N3904 inverter** sits
between the sensor TX and the UART RX pin to restore normal TTL polarity — the
firmware then reads clean frames (no software inversion). `poll()` drains and
parses every loop; `read()` emits the latest range.

**Firmware moves bytes; Python owns meaning** — this emits raw *inches*. The
inches→mm conversion (and the whole-inch quantization note) live node-side in the
[`lv_maxsonar`](../../../../sensors/lv_maxsonar) sensor's `maxsonar` calibration.

`claims: uart` — the contract lists the Serial1 RX pin (D0 on the RA4M1) so it's
reserved; the SBC uplink uses native USB CDC (`Serial`), which claims no GPIO.
Datasheet: <https://cdn.shopify.com/s/files/1/0550/8091/0899/files/11832.pdf>.
