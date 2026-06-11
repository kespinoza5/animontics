# MLX90640 Thermal Camera

Melexis MLX90640 32×24 pixel far-infrared array. Temperature range −40 to +300 °C. Outputs at 8 Hz in this configuration.

## Wiring

```
MLX90640 Breakout   Board I2C
─────────────────   ─────────
VIN (3.3 V)  ──→   3.3 V
GND          ──→   GND
SDA          ──→   SDA  (/dev/i2c-3)
SCL          ──→   SCL
```

**I2C speed:** The MLX90640 requires 400 kHz (Fast Mode) or 1 MHz (Fast Mode+). Set via `tools/board/setup_i2c.sh`.

Default I2C address: `0x33`.

## Config

```yaml
- id: thermal_rear
  type: mlx90640
  enabled: true
  connection:
    type:    i2c
    bus:     3
    address: 0x33
```

## Data — two lanes

The thermal array runs fast (up to 32 fps) and shares the rpi5 with a 30 fps USB
camera + inference, so the full 768-pixel array is **not** sent as JSON. The
sensor emits two independent streams:

### JSON reading lane — lean summary

`GET /sensors/<id>/stream` (SSE) and `/sensors/<id>/ws` carry only the scene
summary, so serialising it 32×/s is cheap and `GET /sensors/<id>` is a light
snapshot:

```json
{
  "sensor_id":   "thermal_rear",
  "sensor_type": "mlx90640",
  "timestamp":   1717000000.0,
  "data": { "min_temp": 19.8, "max_temp": 36.7, "width": 32, "height": 24 }
}
```

### Binary frame lane — the pixel array

`ws://<host>:8080/sensors/<id>/frames` (WebSocket, binary) carries the full
array as a packed little-endian frame. This avoids `json.dumps` of 768 floats
on the node and a parse + GC of a big array on the client — a zero-copy
`Float32Array` view decodes it directly.

```
offset 0    uint32   frame_id      monotonic; client drops duplicate ids
offset 4    float32  min_temp °C
offset 8    float32  max_temp °C
offset 12   float32 × 768  pixels  row-major 32×24 (i = row*32 + col), °C
                                    total = 12 + 768*4 = 3084 bytes
```

Zero-length messages are keepalive pings. `web/viewers/mlx90640.html` consumes
this lane.

## Calibration

The driver reads all 832 EEPROM words on startup and extracts full per-pixel calibration (alpha, offset, kta, kv, CP, gain, PTAT, VDD, KsTa, KsTo). Compensation follows datasheet §11. See `driver.py` for implementation.

## Dev Tools

```bash
# Generate a heatmap PNG from a live frame
python3 mlx90640_heatmap.py

# OpenCV live viewer
python3 view_thermal.py

# Bench viewer: open web/viewers/mlx90640.html (repo root) in a browser,
# enter the board IP + sensor id. Consumes the node's binary frame lane
# (/sensors/{id}/frames) on port 8080 — palettes, denoise, crosshair, auto-range.
```
