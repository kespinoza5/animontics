# mq_array — MQ gas sensor array

An array of MQ-series gas sensors (MQ-2/3/5/6/7/8/9/135, …) read as raw ADC
values that arrive over a microcontroller's serial uplink rather than from a bus
the SBC speaks directly. The MCU firmware is composed and flashed with
[`tools/forge`](../../docs/forge.md); this package is the node-side half that
decodes the stream and serves it like any other sensor.

```
MQ sensors (analog) → MCU ADC → forge link protocol (USB serial) → node → SSE
```

It is a thin `mq_array` subclass of `core.analog_array.AnalogArrayBase`, which
owns the serial read loop and frame decoding. The sensor is decoupled from the
MCU: any board built by forge that streams the same number of channels works.

## Hardware

Each MQ sensor outputs an analog voltage across its load resistor. Wire each to
one ADC channel on the MCU (e.g. an ATmega328P Nano: A0–A7). Which gas sits on
which channel, and the load resistor / clean-air baseline used for calibration,
are recorded in config — not in firmware.

## Configuration

The sensor's `channels` map binds each frame index to a gas signal and its
calibration. Author it consistently with the MCU's forge contract
(`config/mcus/<id>.yaml`); the index order is the wire order the firmware emits.

```yaml
# config/boards/<node-id>.yaml  (gitignored)
sensors:
  - id: gas_array
    type: mq_array
    connection:
      type: uart
      port: /dev/serial/by-id/usb-...-if00   # the MCU's USB serial device
      baud_rate: 115200
    channels:
      - {index: 0, signal: mq135, calibration: {type: raw}}
      - {index: 1, signal: mq2,   calibration: {type: mq, rl: 10000, r0: 76000}}
      # ...
```

- `calibration: {type: raw}` — emit raw counts only (the default; always present).
- `calibration: {type: mq, rl, r0}` — also emit the `Rs/R0` ratio for that signal.
  `rl` is the load resistor (ohms); `r0` is the clean-air baseline (ohms),
  measured per unit. Converting `Rs/R0` to ppm needs per-gas curve constants and
  is deferred.

## Data format

JSON readings on the standard SSE lane (`/sensors/<id>/stream`):

```json
{
  "sensor_id": "gas_array",
  "sensor_type": "mq_array",
  "timestamp": 1717000000.0,
  "data": {
    "seq": 42,
    "raw":   {"mq135": 412, "mq2": 388},
    "ratio": {"mq2": 1.83}
  }
}
```

`raw` is always present (raw ADC counts per signal). `ratio` (Rs/R0) appears only
for channels with `calibration.type: mq`. Clients own any ppm conversion.

> Driving the MCU's PWM outputs (fans) is **not** done through this sensor — that
> is an actuator concern handled by a separate device/actuator path that shares
> the MCU link. See [docs/forge.md](../../docs/forge.md).

## Tests

```bash
pytest sensors/mq_array/ -v      # gas math + enrich; no hardware needed
```
