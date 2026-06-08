# config/mcus/ — MCU build contracts

One file per microcontroller, `config/mcus/<id>.yaml`. It is the **source of
truth** `tools/forge` reads to compose, compile, and flash that MCU's firmware,
and it carries the channel→signal map the node-side array sensor reads back. See
[`docs/forge.md`](../../docs/forge.md) for the design and
[`tools/forge/README.md`](../../tools/forge/README.md) for the commands.

- `example.yaml` — tracked template; copy it to `config/mcus/<your-id>.yaml`.
- `<id>.yaml` — **gitignored** (names a physical unit and holds calibration).

```bash
python -m tools.forge.forge validate <id>     # static-check the contract
python -m tools.forge.forge build    <id>     # compose + compile → firmware/<id>/
python -m tools.forge.forge channels <id>     # print the canonical channels block
```

## Fields

| Field | Meaning |
| --- | --- |
| `id` | MCU instance id (matches the file stem and a node's `usb_mcus[].id`). |
| `target` | Builder key → source tree. `mcu.arduino` ⇒ `mcu/arduino/` + `ArduinoBuilder`. |
| `board` | Board profile in that family's `platform.yaml` (→ FQBN). |
| `transport` | How the node reads the uplink: `{type: serial, baud: …}`. |
| `modules` | Reusable source modules to build in, with pins/params. Each is validated against its `mcu/<family>/modules/<name>/manifest.yaml`. |
| `channels` | The index→signal+calibration map. Order MUST match the module/pin order (validated). Hand-authored so the file stays readable; `forge channels <id>` prints the canonical block. |

## The two consumers

The same file is read at **build time** (forge composes firmware from `modules`
and assigns each provided channel a wire `index`) and at **run time** (the
node-side `mq_array`/`pressure_array` sensor reads `channels` to label and
calibrate the stream). The channel-count/order invariant is checked on every
`validate`/`build`, so firmware and node can't silently disagree on shape.

> `channels` here is the **single source** for the signal/calibration map. A
> device-fed sensor in the board config just lists `devices: [<id>, …]`, and
> `forge resolve <node>` derives its `channels` from these contracts — author once.
> (`animon deploy` calling resolve end-to-end is the remaining fleet seam.)

## Firmware moves bytes; Python owns meaning

Contracts never describe *interpretation* in firmware terms. `calibration` is
opaque data the node applies (e.g. `{type: mq, rl, r0}` → Rs/R0 on the node); the
MCU only ever streams raw counts. Keep it that way.
