# LV-MaxSonar-EZ Ultrasonic Sensor

MaxBotix LV-MaxSonar-EZ series ultrasonic rangefinder. Range 0–254 inches (~6.5 m), 10 Hz output.

## Wiring

```
LV-MaxSonar-EZ      Board UART
──────────────────  ──────────
+5V          ──→    5 V
GND          ──→    GND
TX (pin 5)   ──→    RX  (/dev/ttyS0)
```

The sensor outputs ASCII frames continuously — no trigger needed.

## Config

```yaml
- id: sonar_side
  type: lv_maxsonar
  enabled: true
  connection:
    type:      uart
    port:      /dev/ttyS0
    baud_rate: 9600
```

For Pi Zero 2W connected to OrangePi via USB gadget, the port is `/dev/ttyAMA0` on the Pi Zero side.

## Data

```json
{
  "sensor_id":   "sonar_side",
  "sensor_type": "lv_maxsonar",
  "timestamp":   1717000000.0,
  "data": {
    "distance_mm": 584,
    "strength":    null,
    "temp_c":      null
  }
}
```

## Protocol

ASCII CR-terminated frames at 9600 baud:

```
R023\r   = 23 inches = ~584 mm
```

Format: `R` + 3-digit integer (inches, zero-padded). See `driver.py`.

## Dev Tools

```bash
# Live console output
python3 test_sensor.py

# Open viewer.html in browser, enter board IP
```
