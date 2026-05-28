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

## Data

```json
{
  "sensor_id":   "thermal_rear",
  "sensor_type": "mlx90640",
  "timestamp":   1717000000.0,
  "data": {
    "pixels":   [20.1, 20.3, ...],
    "min_temp": 19.8,
    "max_temp": 36.7,
    "width":    32,
    "height":   24
  }
}
```

`pixels` is a 768-element list (row-major, 32 columns × 24 rows). Index `i = row * 32 + col`. Temperature in °C, rounded to 2 decimal places.

## Calibration

The driver reads all 832 EEPROM words on startup and extracts full per-pixel calibration (alpha, offset, kta, kv, CP, gain, PTAT, VDD, KsTa, KsTo). Compensation follows datasheet §11. See `driver.py` for implementation.

## Dev Tools

```bash
# Generate a heatmap PNG from a live frame
python3 mlx90640_heatmap.py

# OpenCV live viewer
python3 view_thermal.py

# Open viewer.html in browser, enter board IP
```
