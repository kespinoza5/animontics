# TF Mini Plus LiDAR

Benewake TF Mini Plus laser rangefinder. Range 0.1–12 m, output at 100 Hz.

## Wiring

```
TF Mini Plus         Board UART
─────────────────    ──────────
VCC (5 V)    ──→     5 V
GND          ──→     GND
TX           ──→     RX  (/dev/ttyAMA0 pin 10)
RX           ──→     TX  (/dev/ttyAMA0 pin 8)
```

Enable UART on Raspberry Pi / OrangePi: `tools/board/setup_uart.sh`

## Config

```yaml
- id: lidar_front
  type: tf_mini
  enabled: true
  connection:
    type:      uart
    port:      /dev/ttyAMA0
    baud_rate: 115200
```

## Data

```json
{
  "sensor_id":   "lidar_front",
  "sensor_type": "tf_mini",
  "timestamp":   1717000000.0,
  "data": {
    "distance_mm": 1234,
    "strength":    450,
    "temp_c":      25.3
  }
}
```

`strength` is signal amplitude (higher = cleaner return). `temp_c` is the chip temperature, not the environment.

## Protocol

9-byte binary frame at 115200 baud:

```
[0x59][0x59][DL][DH][SL][SH][TL][TH][CS]
 header      dist cm    strength   temp raw  checksum
```

Checksum = sum(bytes 0–7) & 0xFF. See `driver.py`.

## Dev Tools

```bash
# Live console output
python3 test_sensor.py

# Raw byte dump (for debugging framing issues)
python3 test_raw.py

# Bench viewer: open web/viewers/tf_mini.html (repo root) in a browser,
# enter the board IP + sensor id. Connects to the node's
# /sensors/{id}/stream SSE on port 8080.
```
