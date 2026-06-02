# IR Transceiver (ir_xcvr)

TSOP38238 IR receiver + TSAL6200 IR emitter via Linux LIRC. Receives and decodes NEC/NECX IR remote codes and transmits them on demand via the node HTTP API.

## Hardware

| Part | Role | Interface |
|---|---|---|
| TSOP38238 | Demodulating IR receiver | PH10/IR_RX → `/dev/lirc0` via sun4i-ir |
| TSAL6200 | 940 nm IR LED emitter | PH0/PWM3 → `/dev/lirc1` via pwm-ir-tx overlay |
| NPN transistor (2N2222 / S8050) | Current amplifier for TSAL6200 | Between PH0 and LED |

### Wiring

```
┌─────────────────── TSOP38238 ─────────────────────┐
│                                                    │
│  VS  ──── 100 Ω ──── 5 V (13-pin header VCC)       │
│        └── 100 nF ── GND   ← decoupling required   │
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

The 100 Ω + 100 nF supply filter on the TSOP38238 is specified in the datasheet and prevents false triggers from supply noise.  Do not omit it.

The 33 Ω resistor limits TSAL6200 peak current to ~100 mA `(5V − 1.35V − 0.2V) / 33Ω`.  Use 68 Ω for ~50 mA if range is not a concern.

### Kernel setup

Two kernel modules must be loaded:

```bash
# IR receiver decoder (usually autoloaded with sun4i-ir)
modprobe sun4i-ir
modprobe ir-nec-decoder

# TX: pwm-ir-tx via device tree overlay
# In /boot/armbianEnv.txt add:
#   overlays=pwm-ir-tx
# or apply a custom overlay pointing pwm-ir-tx at PWM channel 3 (PH0)
```

Verify devices are present:

```bash
ls -la /dev/lirc*
# expected: /dev/lirc0  (RX)   /dev/lirc1  (TX)
```

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

**RX-only node** (no emitter wired):

```yaml
connection:
  type: ir
  rx_device: /dev/lirc0
```

**TX-only node** (no receiver wired):

```yaml
connection:
  type: ir
  tx_device: /dev/lirc1
```

## Data

Received codes are broadcast as `SensorReading` events on the standard SSE/WebSocket stream:

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

`repeat: true` is set when the same key is held down.  The address and command still reflect the original code.

## HTTP API

### Receive stream

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

Returns `503` if no TX device is configured or the lirc device failed to open.

```
GET  /ir/capabilities    — { can_receive, can_transmit, healthy }
GET  /ir/protocols       — list of supported TX protocols
```

## Node setup note

This sensor adds routes at `/ir/…` that are not part of the standard sensor
router.  Unlike other sensor packages, it requires one additional line in
`node/app.py` to include the IR router:

```python
from node.routers.ir_xcvr import router as ir_xcvr_router
from node.routers.ir_xcvr import register_sensors as register_sensors_ir
…
app.include_router(ir_xcvr_router)
register_sensors_ir(active_sensors)
```

This is already present in the main `node/app.py`.  Boards that do not use
this sensor may leave it in place — the router returns 404 if no `ir_xcvr`
sensor is configured.

## Protocol

NEC standard (32-bit):
```
Header:  9000 µs pulse + 4500 µs space
Bit 0:    562 µs pulse +  562 µs space
Bit 1:    562 µs pulse + 1688 µs space
Stop:     562 µs trailing pulse
Layout:  [addr(8)] [~addr(8)] [cmd(8)] [~cmd(8)]  — LSB first
```

NEC Extended uses a 16-bit address without the address complement check.
Addresses 0-255 encode as standard NEC; 256-65535 auto-upgrade to NECX.

See `codec.py` for the encoder/decoder and `test_codec.py` for a full test
suite that runs without hardware.

## Dev tools

```bash
# Run codec unit tests (no hardware required, works on any OS):
pytest sensors/ir_xcvr/test_codec.py -v

# Hardware debug on the node — listen for any IR remote:
python3 sensors/ir_xcvr/test_hardware.py rx

# Send a test code:
python3 sensors/ir_xcvr/test_hardware.py tx --addr 0x04 --cmd 0x08

# Loopback: emit and receive back (emitter aimed at receiver):
python3 sensors/ir_xcvr/test_hardware.py loopback

# Open viewer.html in a browser and enter the board IP
```
