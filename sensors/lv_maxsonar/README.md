# LV-MaxSonar-EZ Ultrasonic Sensor

MaxBotix LV-MaxSonar-EZ series ultrasonic rangefinder (e.g. **MB1010 EZ1**).
Range 0–254 inches (~6.5 m), ~20 Hz output. Two outputs: an analog voltage (AN
pin, ratiometric `Vcc/512` per inch) and an ASCII serial line (TX pin).
Datasheet: <https://cdn.shopify.com/s/files/1/0550/8091/0899/files/11832.pdf>.

> **The TX line is inverted.** Pin 5 (TX) is "RS232-format" at 0–Vcc levels — i.e.
> *inverted* relative to a TTL UART, idling LOW. A standard UART reads it as
> garbage. It must be inverted before any TTL UART (or read with an inverted
> software UART). See `memory/project_lv_maxsonar_inverted_tx.md`.

## Two deployment modes

The package dispatches on config shape (`sensor.create_lv_maxsonar`):

### 1. Direct UART (SBC reads it)

`connection:` set. The SBC reads `R<NNN>\r` directly — but because TX is inverted,
put a **hardware inverter** (74HC14 Schmitt, or a single 2N3904 + 10 k pull-up)
between the sensor TX and the SBC RX. Output idles high (normal TTL) after the
inverter and the existing `driver.parse_line` decodes it.

```
LV-MaxSonar TX (pin 5) ──▶ [inverter] ──▶ SBC RX (e.g. /dev/ttyS0)
+5V → 5V,  GND → GND
```

```yaml
- id: sonar_side
  type: lv_maxsonar
  enabled: true
  connection: { type: uart, port: /dev/ttyS0, baud_rate: 9600 }
```

### 2. Device-fed via an MCU (the LR4Z path)

`devices:`/`channels:` set, no `connection`. An MCU (e.g. the **LR4Z** RA4M1)
reads the sonar and streams a value per channel over its `mcu_serial` uplink;
the node converts to `distance_mm` via a `maxsonar` calibration. The two lanes
are independent sensor instances so either can move boards later:

```yaml
# Digital lane — firmware serial_sonar parsed R<NNN> → inches
- id: sonar_digital
  type: lv_maxsonar
  devices: [lr4z]
  channels:
    - { device: lr4z, index: 2, signal: sonar_in,
        calibration: { type: maxsonar, mode: inches } }

# Analog lane — raw AN ADC counts (AREF=5 V → ratiometric); scale is bench-set
- id: sonar_analog
  type: lv_maxsonar
  devices: [lr4z]
  channels:
    - { device: lr4z, index: 1, signal: sonar_an,
        calibration: { type: maxsonar, mode: counts, scale: 12.7 } }
```

`maxsonar` calibration:

| mode | channel value | `distance_mm` |
|------|---------------|---------------|
| `inches` | range in inches (firmware parsed `R<NNN>`; `-1` = no reading) | `round(inches · 25.4)` |
| `counts` | raw AN ADC counts | `round(counts · scale)` — `scale` is mm/count, bench-set, absorbs the ADC reference |

> The analog lane relies on **AREF tied to 5 V** on the MCU
> (`analogReference(AR_EXTERNAL)`), so the ratiometric AN output and the ADC share
> a reference. With explicit `scale` the calibration absorbs the reference either
> way.

**Resolution caveat:** the MB1010 reports *whole inches*, so `distance_mm` is
quantized to ~25 mm steps (1 inch = 25.4 mm). That's the sensor's output
resolution, not a precision figure.

## Data

```json
{
  "sensor_id": "sonar_digital",
  "sensor_type": "lv_maxsonar",
  "data": { "distance_mm": 584, "strength": null, "temp_c": null }
}
```

Device-fed mode also carries `raw` (the channel value) and `seq` (frame number).

## Protocol

ASCII CR-terminated frames at 9600 baud: `R023\r` = 23 inches (~584 mm). Format:
`R` + 3-digit integer (inches, zero-padded). See `driver.py`. On the MCU path the
firmware `serial_sonar` module does this parse and streams the inches value.

## Dev Tools

```bash
# Live console output (direct UART)
python3 validate_sensor.py

# Bench: bring-up & protocol reverse-engineering helpers
python3 validate_ads.py        # ADS1115 analog read
python3 validate_correlate.py  # correlate ADS analog vs the raw serial bytes

# Viewer: web/viewers/lv_maxsonar.html (consumes /sensors/{id}/stream)
```
