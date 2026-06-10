# sara_r5_gnss — SARA-R5 GNSS Sensor

GNSS position, velocity, and fix quality from the u-blox SARA-R5 modem's
integrated GNSS engine (SARA-R510M8S variant or any SARA-R5 with AT+UGPS support).

## How it works

This sensor has no UART port of its own. It subscribes to NMEA sentence push
callbacks from a [`sara_r5` device](../../core/device.py), which owns UART5 and
runs the AT command engine. The device routes `$Gx...` sentences to this sensor;
the sensor merges GGA + RMC fields and emits one `SensorReading` per GGA sentence.

```
UART5 → SaraR5Device → subscribe_gnss() → SaraR5GnssSensor → SSE / WebSocket
```

## Wiring

| Signal | Orange Pi pin | Direction |
|--------|--------------|-----------|
| UART5_TX | — | SBC → modem |
| UART5_RX | — | modem → SBC |
| Power enable | PI6 (GPIO 262) | SBC → modem |
| Reset | PI16 (GPIO 272) | SBC → modem |
| TP (PPS) | optional | modem → SBC |

The UART and GPIO are configured on the **sara_r5 device**, not this sensor.

## Board config (`config/boards/<node-id>.yaml`)

```yaml
devices:
  - id: sara_r5_1
    kind: sara_r5
    port: /dev/ttyS5
    baud: 115200
    params:
      gpio_power: 262   # PI6 sysfs GPIO number
      gpio_reset: 272   # PI16 sysfs GPIO number

sensors:
  - id: gnss_1
    type: sara_r5_gnss
    devices: [sara_r5_1]
```

## Data keys

| Key | Type | Description |
|-----|------|-------------|
| `latitude` | `float \| None` | Decimal degrees (negative = South) |
| `longitude` | `float \| None` | Decimal degrees (negative = West) |
| `alt_m` | `float \| None` | Altitude above mean sea level (m) |
| `fix_quality` | `int \| None` | 0=none, 1=GPS, 2=DGPS, 4=RTK, 5=float RTK |
| `satellites` | `int \| None` | Satellites used in fix |
| `hdop` | `float \| None` | Horizontal dilution of precision |
| `speed_kph` | `float \| None` | Speed over ground (km/h) |
| `heading_deg` | `float \| None` | Course over ground — true north (°) |
| `utc_time` | `str \| None` | ISO-8601 UTC timestamp from receiver |
| `rmc_valid` | `bool \| None` | `True` when RMC reports an active fix |

## GNSS enable

The `SaraR5Device` sends `AT+UGPS=1,1` on startup to enable the GNSS engine
with all NMEA sentences. No additional configuration is needed on this sensor.

## TP (time pulse / PPS)

The SARA-R5's TP pin outputs a 1 Hz GPS-synchronised pulse. It is routed to the
SBC but not currently wired in code. See `TODO.md` for the planned GPIO interrupt
implementation.
