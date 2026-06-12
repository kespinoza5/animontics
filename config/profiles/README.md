# config/profiles — SBC pin-capability profiles (tracked)

One YAML file per **board model**, keyed by the `node_type` every node/board
config already carries (`raspberry_pi_zero_2w`, `orangepi_zero2`, …). Unlike
everything else under `config/`, these are **tracked**: pin capabilities are
hardware facts about a board model, not fleet-specific wiring or secrets.

They are the SBC twin of `mcu/<family>/boards/` — `animon deploy` validates a
board config's pin references against the profile for its node_type:

- **libgpiod line specs** (a power_rail's `backend.line`, a speaker's
  `sd_line`, a device's `power_line`/`reset_line` params): the chip name must
  match, and the line offset must be a known header GPIO. Wrong chip is an
  **error**; an offset missing from the table is an error when the table is
  `complete: true`, a warning when partial.
- **`sbc_pwm` backends**: the pwmchip must exist in the profile (**error**),
  and deploy prints a **warning** naming the device-tree overlay it depends
  on — overlay *activation* is live board state that an offline check can't
  see (the seam for a future `animon probe` extension reading
  `/sys/class/pwm` and `/proc/device-tree`).

A node_type with no profile here gets no SBC pin checks (deploy skips
silently). Two layers, deliberately separate: **silicon** (what a pin can
ever do — error material) vs **activation** (what an overlay must enable —
warning material).

## Schema

See [example.yaml](example.yaml). `gpio.lines` maps header pin names to
kernel line offsets — which also makes the profile the authoritative home for
the "what line number is PI6?" arithmetic, instead of comments in board
configs. Verify entries on a live board with `gpioinfo` / `gpiofind`.
