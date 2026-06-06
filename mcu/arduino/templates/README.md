# mcu/arduino/templates/

The family's sketch skeleton that `forge` fills.

- `main.ino.j2` — fixed structure: includes, the shared `g_frame` buffer + globals,
  the generated `onCommand` dispatch, `setup()` (each module's init), and `loop()`
  (sample at the period → `transport.send`, then actuator `tick`s + `transport.poll`).
  The composer renders each module's jinja fragments into the matching slots and
  emits direct, concrete calls — no runtime registry.
