# mcu/ — firmware source, by chip family

This tree holds the **reusable source** that `tools/forge` composes into per-MCU
firmware. It is to firmware what `sensors/` is to the node: a registry of
building blocks, not finished artifacts. Built firmware lands in the gitignored
`firmware/<id>/`; the per-instance recipe lives in `config/mcus/<id>.yaml`.

```
mcu/
└── <family>/              one chip family (arduino now; samd21, rp2040 reserved)
    ├── platform.yaml      board profiles → FQBN, valid pins per kind, compile/flash tools
    ├── modules/<name>/    a reusable module: manifest + lean C++ lib + jinja fragments
    └── templates/         the family's main skeleton the composer fills
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
| [`arduino/`](arduino/README.md) | implemented | AVR/ATmega328P (Nano/Uno). `analog_in`, `pwm_out`, `gpio_out`, `transport_serial`. |
| `samd21/` | reserved | XIAO SAMD21 + ADS1115 (pressure arrays). |
| `rp2040/` | reserved | power/boot/enable sequencing, IMU. |

Adding a family or a module: see
[CONTRIBUTING.md](../CONTRIBUTING.md#adding-an-mcu-target-firmware-module).
Non-MCU targets (FPGA bitstreams, Hailo/Coral model compiles) are sibling trees
(`fpga/`, `accel/`) behind the same forge `Builder` interface.
