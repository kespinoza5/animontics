# forge — firmware composition & flashing

`forge` is to microcontrollers what `animon` is to Linux nodes: a dev-machine
tool that turns a single desired-state file into a working device. It **composes**
firmware from a per-instance contract plus reusable source modules, **compiles**
it to a flashable artifact, and **flashes** it over the host node's SSH access.

```bash
python -m tools.forge.forge validate <mcu-id>    # static-check the contract
python -m tools.forge.forge build    <mcu-id>    # compose + compile → firmware/<id>/
python -m tools.forge.forge flash    <mcu-id>    # build (if needed) + flash to the target
python -m tools.forge.forge channels <mcu-id>    # print the canonical channel block
python -m tools.forge.forge resolve  <node-id>   # fill a board's device-fed sensor channels from contracts
python -m tools.forge.forge clean    <mcu-id>    # remove firmware/<id>/
```

It is **target-pluggable**: the AVR/Arduino MCU builder is the first target;
FPGA bitstreams and accelerator (Hailo/Coral) model compiles slot in behind the
same `Builder` interface with no change to existing targets.

`validate` (and therefore `build`) also runs **cross-contract checks**
(`cross_contract.py`): contracts that participate in the same scanned-lattice
sweep (`matrix_scan` conductor + `scan_follower` followers) must agree on
`rows` and `max_code`, and the conductor must declare one `ack_pin` per
follower contract — a mismatch decodes garbage on the bench and looks exactly
like a wiring fault, so it fails validation instead. Contracts without a scan
module are unaffected.

## How it fits

```
config/mcus/<id>.yaml   ─┐                         (the contract — source of truth)
mcu/<family>/ modules    ├─► forge ─► firmware/<id>/<id>.hex ─► flash ─► MCU
mcu/<family>/platform.yaml┘                                                │
                                                                          ▼
                              raw int16 frames over USB serial ──► node mq_array sensor ──► SSE
```

The MCU streams **raw channel samples**; all meaning (calibration, gas curves,
units) lives in Python on the node. forge never bakes interpretation into
firmware — that boundary is what lets one contract drive both the build and the
node-side decode.

## The contract — `config/mcus/<id>.yaml`

One file, two consumers (build time and run time). See `config/mcus/example.yaml`.

```yaml
id: larduino
target: mcu.arduino        # builder key → mcu/arduino + ArduinoBuilder
board: nano                # board profile in mcu/arduino/platform.yaml → FQBN
transport: {type: serial, baud: 115200}
modules:
  - {module: analog_in, pins: [A7, A6, A5, A4, A3, A2, A1, A0], sample_hz: 2}
  - {module: pwm_out, pins: [D3, D5, D6], freq_hz: 25000}
  - {module: gpio_out, pins: [D13], blink_ms: 500}
  - {module: transport_serial}
channels:                  # ASSIGNED by `forge build`; edit signal/calibration only
  - {index: 0, source: analog_in.A7, signal: mq135, calibration: {type: raw}}
  # ...
```

`forge build` assigns `channels` deterministically from the modules (wire order =
module/pin order), **preserving** any `signal`/`calibration` you set, and writes
them back. The node-side array sensor reads the same `channels` to label the
stream.

## The source tree — `mcu/<family>/`

```
mcu/arduino/
  platform.yaml             FQBN per board, valid pins per kind, compile/flash tools
  modules/<name>/
    manifest.yaml           platforms, role, claims{kind}, provides{channels}, config, sources
    <name>.h / <name>.cpp   the hand-written, audited lean C++ library
    {decl,setup,read,send,loop}.j2   jinja fragments the composer buckets into main.ino
  templates/main.ino.j2     fixed skeleton: setup() inits modules, loop() ticks + flushes

mcu/circuit_python/
  platform.yaml             board profiles (xiao_samd21/rp2040/feather_m4/…), deploy: copy
  modules/<name>/manifest.yaml   parameterize the generic runtime (no compiled sources)
  templates/code.py.j2      one runtime for all boards: FRAME_SOURCES list + command dispatch
```

The AVR composer emits **direct, concrete calls** (no runtime registry, no
vtables); only the modules an instance uses are compiled in. AVR modules:
`analog_in`, `pwm_out`, `gpio_out`, `transport_serial`. CircuitPython modules:
`ads1115`, `analog_in`, `tach`, `matrix_scan`, `scan_follower`, `pwm_out`,
`servo_out`, `gpio_out`, `transport_serial`.

## Toolchain

`build` shells out to `arduino-cli`. If it is not on `PATH`, forge automatically
runs it inside **WSL** (with Windows→`/mnt` path translation) — the animontics
dev machines keep the AVR toolchain there. One-time setup:

```bash
# in WSL
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
  | BINDIR="$HOME/.local/bin" sh
arduino-cli core update-index
arduino-cli core install arduino:avr
```

The on-wire frame format is defined once in `core/mcu_link.py` (the node decodes
with it; `transport_serial` encodes the identical layout). It is versioned —
changing it means bumping `VERSION` there and in the firmware module.

## Adding a target

See [CONTRIBUTING.md](../../CONTRIBUTING.md#adding-an-mcu-target-firmware-module).
A new family is a `mcu/<family>/` tree + modules; a new *category* (FPGA,
accelerator) is a new `Builder` subclass registered in `tools/forge/builders/`.

## Tests (no hardware)

```bash
pytest tools/forge/ -v        # protocol round-trip/resync, contract validation, composer output
```
