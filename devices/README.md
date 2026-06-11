# devices

Device plugin packages — shared peripherals that sensors read **through** and
effectors write **through**, so neither owns the transport. Each subdirectory is a
self-contained package for one device **kind**. The base class + registry +
factory live in [`core/device.py`](../core/device.py); this tree holds the
concrete kinds, auto-discovered exactly like `sensors/`, `effectors/`, `policies/`.

## Plugin system

`devices/__init__.py` uses `pkgutil.iter_modules` to import every package on disk,
firing each `@register_device("kind")`. `node/app.py` imports `devices` once;
instances are created from the board config's `devices:` list (started before the
sensors/effectors that bind to them by id).

## Available kinds

| Package | Kind | Model | Transport |
|---------|------|-------|-----------|
| [`mcu_serial/`](mcu_serial/README.md) | `mcu_serial` | push (frames out, commands in) | MCU serial link (`core/mcu_link.py`) |
| [`ads1115/`](ads1115/README.md) | `ads1115` | pull (muxed single-shot reads) | ADS1115 ADC on I2C |
| [`sara_r5/`](sara_r5/README.md) | `sara_r5` | mixed (NMEA push + AT poll) | u-blox SARA-R5 modem on UART |
| [`si5351/`](si5351/README.md) | `si5351` | configure-at-boot (no data) | Si5351A clock generator — the audio clock tree's root |

## Adding a device

Subclass `Device`, decorate `@register_device("kind")`, and implement
`start/stop/is_healthy`. Push devices fan decoded data to subscriber callbacks
(and may offer a command sink); pull devices expose a read method. Declare under
`devices:` in the board config. Pins/GPIO a device toggles go through the portable
[`core/gpio.py`](../core/gpio.py) output-line abstraction, not hard-coded sysfs.
See [CONTRIBUTING.md](../CONTRIBUTING.md#adding-a-device-effector-or-policy).
