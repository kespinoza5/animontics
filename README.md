# IR Transceiver (ir_xcvr)

TSOP38238 IR receiver + TSAL6200 IR emitter via Linux LIRC. Receives and
decodes NEC/NECX IR remote codes; transmits them on demand via the node HTTP
API.  Both devices are optional — the sensor degrades gracefully when either
is absent.

---

## Hardware

| Part | Role | Interface |
|---|---|---|
| TSOP38238 | Demodulating IR receiver, 38 kHz | PH10/IR_RX → `/dev/lirc0` via `sun4i-ir` |
| TSAL6200 | 940 nm IR LED emitter | PH0/PWM3 → `/dev/lirc1` via `pwm-ir-tx` overlay |
| NPN transistor (2N2222 / S8050) | Current amplifier for TSAL6200 | Between PH0 and LED |

### Wiring

```
┌─────────────────── TSOP38238 ─────────────────────┐
│                                                    │
│  VS  ──── 100 Ω ──── 5 V (13-pin header VCC)       │
│        └── 100 nF ── GND   ← required by datasheet │
│  GND ────────────── GND                            │
│  OUT ────────────── PH10 / IR-RX (13-pin header)   │
└────────────────────────────────────────────────────┘

┌─────────────────── TSAL6200 ───────────────────────┐
│                                                    │
│  5 V ── 33 Ω ── anode                              │
│                 cathode ── NPN collector            │
│  PH0 (CPUX-UTX) ── 1 kΩ ── NPN base                │
│                             NPN emitter ── GND      │
└────────────────────────────────────────────────────┘
```

**100 Ω + 100 nF on TSOP38238 supply** — specified in the datasheet to
suppress supply-line noise that causes false triggers.  Do not omit it.

**33 Ω current-limit resistor** — limits TSAL6200 peak current to ~100 mA:
`(5 V − 1.35 V − 0.2 V) / 33 Ω`.  Use 68 Ω for ~50 mA if range is not a
concern.

**1 kΩ base resistor** — the GPIO sources only ~8 mA; the transistor
amplifies this to drive the LED.  At 3.3 V: `(3.3 − 0.7) / 1000 = 2.6 mA`
base current saturates any of the listed transistors well below their h_FE
knee.

---

## Kernel setup

### RX — `sun4i-ir`

The Allwinner `sun4i-ir` hardware IR decoder is usually enabled by default in
Orange Pi Armbian images and auto-loads `ir-nec-decoder`.  Verify:

```bash
lsmod | grep -E 'sun4i|ir_nec'
ls /dev/lirc*          # expect /dev/lirc0
```

If `/dev/lirc0` is absent, add to `/boot/armbianEnv.txt`:

```
overlays=ir-rx
```

### TX — `pwm-ir-tx` device tree overlay

There is no stock `pwm-ir-tx` overlay for PH0/PWM3 in most Orange Pi images.
You need to compile and install a custom DTS fragment.

**`pwm-ir-tx-ph0.dts`**

```dts
/dts-v1/;
/plugin/;

/ {
    compatible = "allwinner,sun50i-h616";

    /* Fragment 0: mux PH0 to PWM3 function */
    fragment@0 {
        target = <&pio>;
        __overlay__ {
            ir_tx_pin: ir-tx-pin {
                pins          = "PH0";
                function      = "pwm3";
                drive-strength = <10>;
            };
        };
    };

    /* Fragment 1: enable the PWM3 hardware block */
    fragment@1 {
        target = <&pwm3>;
        __overlay__ {
            status = "okay";
        };
    };

    /* Fragment 2: register a pwm-ir-tx LIRC device on that channel */
    fragment@2 {
        target-path = "/";
        __overlay__ {
            ir-transmitter {
                compatible    = "pwm-ir-tx";
                pwms          = <&pwm3 0 0 0>;
                pinctrl-names = "default";
                pinctrl-0     = <&ir_tx_pin>;
                status        = "okay";
            };
        };
    };
};
```

**What each fragment does:**

- **Fragment 0** reaches into the pin controller (`&pio`) and declares a
  pinctrl state that routes PH0 to the PWM3 peripheral.  Without this the pin
  stays muxed as UART0_TX and PWM3 never reaches it.
- **Fragment 1** gates on the PWM3 clock — all Allwinner peripherals default
  to `status = "disabled"` to save power.
- **Fragment 2** creates the `pwm-ir-tx` platform device.  The `pwms` property
  hands it a reference to the PWM channel; `pinctrl-0` ties fragment 0's pin
  state to this device so the mux switch happens when the device is probed.
  The kernel driver registers with the LIRC subsystem, producing `/dev/lirc1`.

**Install:**

```bash
# On the board (requires device-tree-compiler)
dtc -@ -I dts -O dtb -o /boot/overlay-user/pwm-ir-tx-ph0.dtbo pwm-ir-tx-ph0.dts

# Add to /boot/armbianEnv.txt
user_overlays=pwm-ir-tx-ph0

reboot
```

Verify after reboot:

```bash
ls /dev/lirc*          # expect /dev/lirc0 (RX) and /dev/lirc1 (TX)
```

---

## Config

```yaml
- id: ir_xcvr
  type: ir_xcvr
  enabled: true
  connection:
    type: ir
    rx_device: /dev/lirc0   # omit to disable RX
    tx_device: /dev/lirc1   # omit to disable TX
```

**RX-only** (no emitter wired):

```yaml
connection:
  type: ir
  rx_device: /dev/lirc0
```

**TX-only** (no receiver wired):

```yaml
connection:
  type: ir
  tx_device: /dev/lirc1
```

---

## Code architecture

The package is split into three layers so each can be tested and reasoned
about independently.

```
codec.py    — IR protocol logic.  Pure Python, no hardware, no imports
              outside stdlib.  Runs on any OS.

driver.py   — Linux LIRC device I/O.  Opens file descriptors, calls ioctl,
              reads/writes structs.  No threading, no Pydantic, no animontics.
              Imported by test_hardware.py without the full stack.

sensor.py   — animontics integration.  Owns the background thread, retry
              loop, SensorBase lifecycle, and the transmit() public method.
              Delegates all hardware calls to driver.py and all protocol
              work to codec.py.
```

### `codec.py` — protocol layer

NEC encodes bits as **pulse-distance modulation**: every bit is a fixed-width
562 µs carrier burst (the mark), followed by a space whose length determines
the bit value — 562 µs for 0, 1688 µs for 1.  A 9 ms / 4.5 ms header that
no bit-period can produce marks the frame start.

```
Header:  9000 µs pulse  +  4500 µs space
Bit 0:    562 µs pulse  +   562 µs space
Bit 1:    562 µs pulse  +  1688 µs space
Stop:     562 µs trailing pulse
```

The 32-bit frame layout (LSB-first):

```
[addr(8)] [~addr(8)] [cmd(8)] [~cmd(8)]
```

The complement bytes are an integrity check — if `addr XOR ~addr ≠ 0xFF` the
frame is corrupt.  NEC Extended drops the address complement and uses both
bytes as a 16-bit address; `codec.py` auto-detects this on decode via the
same XOR check.  On encode, passing `address > 255` silently promotes to NECX.

`decode_nec` applies ±40 % timing tolerance on every mark and space so
real-world remotes with off-spec oscillators still decode.

`encode_nec` returns a flat `list[int]` of microsecond durations — the same
format LIRC mode2 TX expects.  `encode_nec_repeat` returns the three-pulse
repeat code a remote sends when a key is held down.

### `driver.py` — LIRC I/O layer

The Linux LIRC subsystem exposes two interfaces depending on the kernel
version and which driver module is loaded:

**Scancode mode** (`LIRC_MODE_SCANCODE`) is the preferred path.  After
`ioctl(fd, LIRC_SET_REC_MODE, LIRC_MODE_SCANCODE)` each `read()` returns a
24-byte `lirc_scancode` struct:

```c
struct lirc_scancode {
    uint64_t timestamp;   // monotonic nanoseconds
    uint16_t flags;       // LIRC_SCANCODE_FLAG_REPEAT = 0x02
    uint16_t rc_proto;    // protocol enum (NEC=9, NECX=10, RC5=2 …)
    uint32_t keycode;
    uint64_t scancode;    // (address << 8) | command for NEC family
};
```

The kernel's `ir-nec-decoder` module does all pulse timing analysis and
hands you a decoded value.  For TX, writing the same struct to `/dev/lirc1`
causes `pwm-ir-tx` to generate the carrier and pulse sequence.

**Mode2** (`LIRC_MODE_MODE2`) is the fallback for older kernels or drivers
that don't support scancode mode.  Every `read()` returns a 4-byte word —
upper byte is pulse/space/timeout type, lower 24 bits are duration in
microseconds.  On TX, you write alternating pulse/space durations directly
(no type bits — the kernel assumes the first value is a pulse).
`driver.py` passes the accumulated pulse list to `codec.decode_nec` after
seeing a timeout word or a gap > 10 ms.

`open_lirc_rx` and `open_lirc_tx` try scancode mode first and return
`(fd, scancode_mode: bool)`.  That boolean propagates to `sensor.py` so the
correct read/write path is taken throughout the session.

`fcntl` is imported inside a `try/except ImportError` so the module loads on
Windows dev machines without crashing.  Hardware calls will raise at runtime
on non-Linux, which is expected.

### `sensor.py` — animontics integration layer

`IrXcvrSensor` extends `SensorBase` and adds one public method (`transmit`)
for the TX action path.  The standard `SensorBase` interface handles the RX
broadcast side.

**Lifecycle:**
- `start()` opens the TX device (keeping the fd open across calls to avoid
  repeated open/ioctl overhead), then spawns the reader thread if `rx_device`
  is configured.
- `stop()` sets the stop event, joins the thread with a 3 s timeout, and
  closes the TX fd.

**Reader thread — two nesting levels:**
- Outer `_read_loop` is the retry wrapper.  On any device error it logs,
  waits 2 s, and reopens.  This handles driver resets, hot-plug, and boot
  races where the device isn't ready yet.
- Inner `_read_scancode` / `_read_mode2` are the steady-state loops.  Both
  use `select()` with a 0.5 s timeout so the stop event is checked regularly
  even when no IR activity is happening.

**`transmit()` thread safety:**
The method is called from the FastAPI request thread while the background
reader thread is running.  A `threading.Lock` protects the TX fd to prevent
concurrent writes.  `transmit()` acquires the lock, delegates to
`driver.write_scancode` or `driver.write_raw_pulses` (depending on which mode
was negotiated at open time), and returns a bool that the router translates
to HTTP 200 or 500.

**`can_receive` / `can_transmit`** properties let the router report accurate
capability flags — `can_receive` is config-based (is `rx_device` set?),
`can_transmit` checks whether the TX fd is actually open, since the device
open can fail at runtime even when configured.

---

## Data

Received codes are broadcast as `SensorReading` events:

```json
{
  "sensor_id":   "ir_xcvr",
  "sensor_type": "ir_xcvr",
  "timestamp":   1717000000.0,
  "data": {
    "protocol": "NEC",
    "address":  4,
    "command":  8,
    "scancode": 1032,
    "repeat":   false
  }
}
```

`repeat: true` is set when a key is held down.  Address and command still
reflect the original code.

---

## HTTP API

### Receive

```
GET /sensors/ir_xcvr/stream    — SSE stream of received codes
GET /sensors/ir_xcvr/ws        — WebSocket stream
GET /sensors/ir_xcvr           — last received code (or null)
```

### Transmit

```
POST /ir/transmit
Content-Type: application/json

{ "protocol": "NEC", "address": 4, "command": 8 }
```

```json
{ "ok": true, "protocol": "NEC", "address": 4, "command": 8, "scancode": 1032 }
```

Returns `503` if TX is not available (no `tx_device` configured, or the lirc
device failed to open at startup).

```
GET  /ir/capabilities    — { can_receive, can_transmit, healthy }
GET  /ir/protocols       — list of supported TX protocols
```

---

## Node setup note

This sensor adds routes at `/ir/…` that are not part of the standard sensor
router.  Unlike other sensor packages it requires two additional lines in
`node/app.py`:

```python
from node.routers.ir_xcvr import router as ir_xcvr_router
from node.routers.ir_xcvr import register_sensors as register_sensors_ir
…
app.include_router(ir_xcvr_router)
register_sensors_ir(active_sensors)
```

This is already present in the main `node/app.py`.  Boards that do not use
this sensor can leave it in place — the router returns 404 if no `ir_xcvr`
sensor is configured.

---

## Dev tools

```bash
# Codec unit tests — no hardware required, works on any OS:
pytest sensors/ir_xcvr/test_codec.py -v

# Hardware debug on the node — listen for any IR remote (15 s):
python3 sensors/ir_xcvr/test_hardware.py rx

# Send a test NEC code:
python3 sensors/ir_xcvr/test_hardware.py tx --addr 0x04 --cmd 0x08

# Loopback: emit and receive back (aim emitter at receiver, < 10 cm):
python3 sensors/ir_xcvr/test_hardware.py loopback

# Bench viewer: open web/viewers/ir_xcvr.html (repo root) in a browser,
# enter the board IP + sensor id. Live RX log via the node's
# /sensors/{id}/stream SSE on port 8080, plus a TX panel (/ir/transmit).
```
