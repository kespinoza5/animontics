# config/nodes/ — per-board staging configs

This directory holds dev-machine copies of each board's `config.yaml`.
It is **gitignored** — these files contain real wiring details (ports, bus
addresses, baud rates) specific to your hardware.

## Purpose

`animon deploy` and `animon diff` normally read the live config from the board
over SSH. Keeping a local copy here lets you:

- Plan and review changes offline before deploying
- Run `animon deploy --dry-run` without an active SSH connection
- Track wiring changes in your local notes without committing to the repo

## Naming

One file per node, named `<node-id>.yaml` where `node-id` matches the `id`
field in `config/animon.yaml`. Example:

```
config/nodes/
├── my_other_node.yaml
├── my_pizero_node.yaml
├── my_sbc_node.yaml
└── my_hub_node.yaml
```

## Populating

Run `animon pull <node-id>` to fetch the board's live config and write it here.
Or copy `config/config.example.yaml` and fill in the wiring manually.

## Schema

Same schema as the board's `config.yaml` — see `config/config.example.yaml`.
