# sara_r5_lte — SARA-R5 LTE Signal Quality Sensor

LTE-M/NB-IoT signal quality, registration state, and operator name from the
u-blox SARA-R5 modem via polled AT commands.

## How it works

This sensor has no UART port of its own. It holds a reference to a `sara_r5`
device and calls `device.send_at()` every 30 seconds to poll signal quality.

```
SaraR5LteSensor ──AT+CESQ──► SaraR5Device ──UART5──► SARA-R5 modem
                ◄─+CESQ: ...──
```

`send_at()` is the same seam that future SIM/SMS/data use will go through.

## Board config (`config/boards/<node-id>.yaml`)

```yaml
devices:
  - id: sara_r5_1
    kind: sara_r5
    port: /dev/ttyS5
    baud: 115200
    params:
      gpio_power: 262   # PI6
      gpio_reset: 272   # PI16

sensors:
  - id: lte_1
    type: sara_r5_lte
    devices: [sara_r5_1]
```

## Data keys

| Key | Type | Description |
|-----|------|-------------|
| `rsrp_dbm` | `float \| None` | Reference signal received power (dBm) |
| `rsrq_db` | `float \| None` | Reference signal received quality (dB) |
| `rssi_dbm` | `float \| None` | Received signal strength (dBm) |
| `registration_state` | `str \| None` | `registered_home`, `registered_roaming`, `searching`, `denied`, `not_registered` |
| `rat` | `str \| None` | Radio access technology: `LTE_M1`, `NB_IoT`, `LTE`, etc. |
| `operator` | `str \| None` | Network operator name |
| `band` | `str \| None` | Active band / RAT from COPS response |

## Future SIM use

`SaraR5Device.send_at()` is the public seam for sending arbitrary AT commands.
Future capabilities (SMS, data-relay, SIM toolkit) can issue commands directly
through the device without modifying this sensor.
