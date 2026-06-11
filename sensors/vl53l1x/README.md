# VL53L1X Time-of-Flight Distance Sensor

ST Microelectronics VL53L1X. Range up to 4 m (long mode). Uses Class 1 940 nm VCSEL laser.

## Wiring

```
VL53L1X Breakout    Board I2C
────────────────    ─────────
VIN (3.3 V)  ──→   3.3 V
GND          ──→   GND
SDA          ──→   SDA  (/dev/i2c-3 on OrangePi Zero 2)
SCL          ──→   SCL
```

Enable I2C: `tools/board/setup_i2c.sh`

Default I2C address: `0x29`. Multiple sensors on one bus require address reassignment via XSHUT pin.

## Config

```yaml
- id: tof_top
  type: vl53l1x
  enabled: true
  connection:
    type:    i2c
    bus:     3
    address: 0x29
```

## Data

```json
{
  "sensor_id":   "tof_top",
  "sensor_type": "vl53l1x",
  "timestamp":   1717000000.0,
  "data": {
    "distance_mm": 843,
    "strength":    null,
    "temp_c":      null
  }
}
```

`distance_mm` is `null` when the sensor returns a ranging error (out of range, low reflectance, etc.).

## Distance Modes

| Mode | Max range | Use case |
|------|-----------|----------|
| 1 (short)  | ~1.3 m | Best accuracy, lowest ambient light sensitivity |
| 2 (medium) | ~2.0 m | 50 ms timing budget |
| 3 (long)   | ~4.0 m | 100 ms timing budget — **default** |

The driver starts in mode 3. Modes can be switched live at runtime — no
reinit — via the node's `vl53l1x` router:

```
GET  /vl53l1x/state            → {mode, label, max_mm, auto, healthy}
POST /vl53l1x/mode  {mode:1|2|3}  → pin a fixed mode (turns auto off)
POST /vl53l1x/auto  {enabled:bool} → distance-driven auto-ranging
```

Auto-ranging picks the tightest mode that covers the current distance, with a
hysteresis deadband so a reading sitting on a boundary doesn't flap. Mode
changes are also pushed to stream subscribers as named SSE `mode` events, so the
viewer reflects switches it didn't initiate.

## Driver

`driver.py` is a pure smbus2 implementation requiring no Adafruit/Blinka stack. The original sensor server also supported the Adafruit CircuitPython driver as an alternative; that code lives in the `sensors/vl53l1x` submodule git history (pre-migration commits).

`orangepizero2.py` is a custom Blinka board definition for the OrangePi Zero 2 (needed only with the Adafruit driver path).

## Dev Tools

```bash
# Test Blinka/CircuitPython I2C access
python3 test_blinka.py

# Bench viewer: open web/viewers/vl53l1x.html (repo root) in a browser,
# enter the board IP + sensor id. Connects to the node's
# /sensors/{id}/stream SSE on port 8080, with Short/Medium/Long/Auto controls.
```
