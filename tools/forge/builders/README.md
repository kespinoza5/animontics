# tools/forge/builders/ — target builders

One module per forge target type. Each registers a `Builder` subclass with
`@register_builder("<target>")`; `builders/__init__.py` imports them so the
registration fires. A builder implements `validate / compose / build / deploy`
(see `tools/forge/builder.py`).

| Builder | Target | Notes |
|---------|--------|-------|
| `arduino.py` | `mcu.arduino` | render jinja → sketch, compile with arduino-cli (WSL fallback) |
| `circuit_python.py` | `mcu.circuit_python` | render `code.py`, no compile, copy to CIRCUITPY |

New targets are additive — add a module here, import it in `__init__.py`. Future:
`fpga.ice40` (yosys/nextpnr → bitstream), `accel.hailo`/`accel.coral` (model compile).
See [docs/forge.md](../../../docs/forge.md).
