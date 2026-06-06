# mcu/ — firmware source, by runtime

This tree holds the **reusable source** that `tools/forge` composes into per-MCU
firmware. It is to firmware what `sensors/` is to the node: a registry of
building blocks, not finished artifacts. Built firmware lands in the gitignored
`firmware/<id>/`; the per-instance recipe lives in `config/mcus/<id>.yaml`.

Families are organized by **runtime** (which determines the build), not by chip —
one CircuitPython family serves every CP board.

```
mcu/
└── <family>/              arduino (compiled C++) | circuit_python (no compile)
    ├── platform.yaml      board profiles + toolchain/deploy method
    ├── modules/<name>/    a reusable module: manifest + (C++ lib / config schema)
    └── templates/         the family skeleton the composer fills (main.ino / code.py)
```

A **module** is the unit of composition. Its `manifest.yaml` declares the
platforms it supports, its role (`sensor`/`actuator`/`transport`), the pins it
claims, the channels it provides, its config, and its source files. The composer
buckets each module's jinja fragments into the family template and emits **direct,
concrete calls** — no runtime registry, no vtables; only modules an instance uses
are compiled in.

## The firmware↔Python boundary

Firmware moves bytes; Python owns meaning. A module reads/writes pins and frames
the data; it never calibrates, scales, or interprets. All meaning lives in the
node-side sensor (`core/analog_array.py` + `sensors/<type>/`). The on-wire frame
format is defined once in [`core/mcu_link.py`](../core/mcu_link.py) and mirrored
by the `transport_serial` module.

## Families

| Family | Status | Notes |
| --- | --- | --- |
| [`arduino/`](arduino/README.md) | implemented | AVR/ATmega328P (Nano/Uno). Compile lean C++ via arduino-cli. Modules: `analog_in`, `pwm_out`, `gpio_out`, `transport_serial`. |
| [`circuit_python/`](circuit_python/README.md) | implemented | Any CircuitPython board (XIAO SAMD21, RP2040). One generic `code.py`, no compile, copy-deploy. Modules: `ads1115`, `transport_serial`. |
| `micro_python/` | future | MicroPython boards, same ship-files model. |

Adding a family or a module: see
[CONTRIBUTING.md](../CONTRIBUTING.md#adding-an-mcu-target-firmware-module).
Non-MCU targets (FPGA bitstreams, Hailo/Coral model compiles) are sibling trees
(`fpga/`, `accel/`) behind the same forge `Builder` interface.
