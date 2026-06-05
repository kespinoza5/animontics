# firmware/ — build output (not source)

This directory holds **composed and compiled artifacts**, one subdirectory per
MCU instance (`firmware/<id>/`). It is produced by `tools/forge` from:

- the per-instance contract `config/mcus/<id>.yaml` (what to build), and
- the family source modules under `mcu/<family>/` (how to build it).

```bash
python -m tools.forge.forge build <id>     # → firmware/<id>/ (rendered project + .hex)
```

Everything here is a deterministic build product, so it is **gitignored**
(only this README is tracked). Never hand-edit files in `firmware/<id>/` — change
the contract or the `mcu/<family>/` modules and rebuild. See [docs/forge.md](../docs/forge.md).
