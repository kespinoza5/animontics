# sara_r5 — u-blox SARA-R5 LTE-M + GNSS modem device

One physical module on one UART, serving **two** logical sensors. **Mixed model:**

- **GNSS push** — NMEA sentences (`$Gx…`) are fanned to `subscribe_gnss()`
  callbacks as they arrive. Read by [`sara_r5_gnss`](../../sensors/sara_r5_gnss/README.md).
- **LTE poll** — signal/registration status is fetched on demand via `send_at()`.
  Read by [`sara_r5_lte`](../../sensors/sara_r5_lte/README.md). `send_at()` is also
  the public seam for future SIM / SMS / data use.

The single shared UART is exactly why this is a **device**: both sensors are
logical views of it, and neither owns the transport.

## Board config (`config/boards/<node>.yaml`)

```yaml
devices:
  - id: sara_r5_1
    kind: sara_r5
    port: /dev/ttyS5            # OrangePi Zero 2 UART5
    baud: 115200
    params:
      power_line: {backend: libgpiod, chip: gpiochip1, line: 262}   # PI6
      reset_line: {backend: libgpiod, chip: gpiochip1, line: 272}   # PI16
      # init: [ATE0, AT+CMEE=2, AT+CEREG=2, "AT+UGPS=1,1"]   # default enables GNSS
```

## Power / reset pins — portable

The power-enable and reset pins are driven through
[`core/gpio.py`](../../core/gpio.py)'s `make_output_line()`, so this device is not
tied to one board's GPIO scheme:

| `backend` | Use | Spec keys |
|-----------|-----|-----------|
| `libgpiod` | SBC kernel GPIO (Orange Pi, Pi 5) | `chip`, `line`, `active_low` |
| `mcu` | drive the pin through an MCU command (future seam) | `device`, `command`, `channel` |
| `none` | pin not wired / modem powers on by default | — |

Omit a `*_line` spec entirely to leave that pin uncontrolled.

> **Unverified on hardware:** the libgpiod `chip`/`line` values for the Orange Pi
> Zero 2's PI6/PI16 pins (sunxi line offset + gpiochip numbering) still need
> confirming on the board, and the gpiod Python binding major (v1 vs v2) depends on
> the Armbian release. See `TODO.md`.

## GNSS enable

The default `init` sequence sends `AT+UGPS=1,1` (GNSS on, all NMEA sentences).
Override `params.init` to change the AT bring-up.
