# Firmware & Targets (forge)

Animontics has a third tier below the Linux nodes: **microcontrollers** (and,
later, FPGAs and inference accelerators) hanging off a node's USB hubs. Unlike a
sensor the SBC speaks to directly over I2C/UART, these devices run their own
flashed code. `tools/forge` is the dev-machine tool that builds and ships that
code — the MCU-tier counterpart to the `animon` fleet CLI.

For the node and fleet design, see [Architecture](architecture.md). For the
command reference, see [forge tool](tools/forge.md).

## Three tiers

```
dev machine + repo          control plane — animon (nodes) + forge (targets) run here
        │
   Linux nodes (rpi5, neocore2)   slim relays: run node/app.py, expose sensors over SSE
        │
   targets (MCUs, FPGAs, accelerators)   flashed code: sense / actuate / orchestrate
```

A target is reached *through* its host node (it has no IP of its own); forge
flashes it over the host's existing SSH access.

## The one boundary that matters

> **Firmware moves bytes; Python owns meaning.**

Firmware streams raw channel samples (and, later, accepts actuator commands).
Calibration, channel→signal mapping, gas curves, sample policy — all live in
Python on the node. This boundary is fixed across every transport and every
build-sophistication level, which is what lets a single contract drive both the
firmware build and the node-side decode, and lets the node-side sensor stay
identical whether the firmware was hand-tuned or fully generated.

## Build-time composition

Firmware is **composed from config at build time on the dev machine** — not
hand-maintained per board, and not configured on-device. The target receives a
lean artifact with no on-device config parser, no runtime module registry, and no
vtables; only the modules an instance actually uses are compiled in. The composer
emits direct, concrete calls — the generated `main.ino` reads like something a
person would have written by hand.

```
config/mcus/<id>.yaml   ─┐
mcu/<family>/ modules    ├─► forge compose ─► firmware/<id>/ ─► compile ─► <id>.hex ─► flash
mcu/<family>/platform.yaml┘
```

| Concern | Where | In repo? |
| --- | --- | --- |
| Build contract (modules, params, channel map) | `config/mcus/<id>.yaml` | gitignored (per-unit) |
| Family source + capabilities | `mcu/<family>/` (`platform.yaml`, `modules/`, `templates/`) | ✅ |
| Wire protocol codec | `core/mcu_link.py` (node decodes; firmware mirrors) | ✅ |
| Build output | `firmware/<id>/` | gitignored (deterministic rebuild) |
| Node-side interpretation | the array sensor's `channels` in `config/boards/<id>.yaml` | gitignored |

## The contract is the seam

`config/mcus/<id>.yaml` has two consumers. At build time forge reads the
`modules` to compose firmware and assigns each provided channel a deterministic
wire `index`. At run time the node-side array sensor reads the same `channels`
map to label and calibrate the incoming stream. The channel-count invariant
(`len(channels) == channels the modules provide`) is checked on every build, so
firmware and node can never silently disagree on shape.

> The contract's `channels` is the **single authored source** for the
> signal/calibration map. A device-fed sensor lists `devices: [<id>, …]` and
> `forge resolve <node>` derives its `channels` from the contracts — author once.
> (`animon deploy` calling resolve end-to-end is the remaining fleet seam.)

## Target-pluggable

forge dispatches on the contract's `target` key (`mcu.arduino`, later
`fpga.ice40`, `accel.hailo`, …) to a registered `Builder`. Each builder
implements the same four steps — `validate`, `compose`, `build`, `deploy` — so
adding a TinyFPGA bitstream flow (yosys/nextpnr → bitstream) or a Hailo/Coral
model compile is additive: a new builder under `tools/forge/builders/`, with zero
churn to the MCU path. The MCU/Arduino target is the worked example today.

## Toolchain

`forge build` compiles with `arduino-cli`, falling back to running it inside WSL
(with path translation) when it is not on `PATH`. See the
[forge tool page](tools/forge.md) for one-time install steps. The link frame
format lives once in `core/mcu_link.py` and is versioned.

## Families & targets

Firmware families are organized by **runtime**, not chip:

- **`mcu/arduino/`** (`target: mcu.arduino`) — AVR/ATmega328P. Composes lean C++
  from `analog_in`/`pwm_out`/`gpio_out`/`transport_serial` modules and compiles a
  real `.hex` with `arduino-cli` (WSL fallback).
- **`mcu/circuit_python/`** (`target: mcu.circuit_python`) — XIAO SAMD21, RP2040,
  any CircuitPython board. *No compile*: one generic runtime
  (`templates/code.py.j2`) is composed with the instance's chip list into
  `firmware/<id>/code.py`; deploy copies it to the `CIRCUITPY` drive. Both
  stream the same `core/mcu_link.py` frames, so the node device decodes them
  identically. The runtime is **bidirectional**: it streams sensor channels
  (ADS1115, tach RPM) uplink *and* drives PWM outputs from inbound commands —
  whichever modules the contract composes. Current modules: `ads1115`, `tach`
  (fan FG/RPM via hardware edge-counting), `pwm_out`, `transport_serial`.

The MCU↔node command lane is built end to end: `AC` command frames in
`core/mcu_link.py`, `transport_serial.poll()` + a generated `onCommand` dispatch
in firmware, and on the node the **[effector tier](cortex.md)** owns the device
link and sends commands (e.g. driving the fans) — *through the device*, never the
sensor.

## Status

Implemented: the forge core (validate/build/flash/clean/channels/resolve), the
AVR/Arduino target (compose **+** compile to a real `.hex`), the CircuitPython
family (compose a bidirectional runtime — ADS1115 + tach + PWM command lane,
copy-deploy), and the node-side [`mq_array`](sensors/mq_array.md),
[`pressure_array`](sensors/pressure_array.md), and
[`fan_tach`](sensors/fan_tach.md) sensors. `forge resolve` derives a
device-fed sensor's `channels` from its MCU contracts — author the channel map
once. Deferred (reserved behind seams): the **models** tier (accelerator
perception nets — `accel.hailo`/`accel.coral` builders), flash/copy-deploy against
live hardware, SPI transport, FPGA builders, `animon`↔`forge` reconcile, and
protocol v2. See `TODO.md`.
