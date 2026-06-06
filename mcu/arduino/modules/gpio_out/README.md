# gpio_out (arduino module)

Digital outputs with an optional non-blocking heartbeat blink (status LED).
**role:** actuator · **claims:** gpio pins · **config:** `blink_ms` (0 = static).

- `gpio_out.h/.cpp` — `setup()` drives pins LOW; `tick(now)` toggles at `blink_ms`.
- `decl/setup/loop.j2` — instance, `pinMode`, and `tick(now)` in the main loop.

Proves the composer can fold a module with its own `loop()` work into `main.ino`.
