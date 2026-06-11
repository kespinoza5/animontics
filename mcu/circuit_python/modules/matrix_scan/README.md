# matrix_scan (circuit_python module)

The **conductor** of a multi-MCU scanned analog matrix — built for the
velostat pressure lattice: CD4051 muxes energize one high-side row at a time
while this MCU and several follower MCUs sample their share of the lattice's
sense lines. **role:** sensor · **provides:** `channels: 1` (the current row
index — a pin-independent virtual channel).

## Row energization

`pins` are the 3 shared CD4051 select lines (A/B/C) followed by **one inhibit
line per mux**: `rows = 8 × n_inh`, and row *N* maps to inhibit pin `N // 8` +
select code `N % 8`. All other muxes are inhibited while a row is energized.

## The DAC sync handshake

Followers can't see the row lines, so scan phase is broadcast **in analog** —
the same medium the organ senses in. Both sides must agree on `rows` and
`max_code` (cross-contract validation is manual today; see TODO.md):

```
code(row) = (row + 1) * max_code // (rows + 1)      idle = 0
decode tolerance = ± half a step
```

Per tick the conductor: advances the row → energizes it → broadcasts
`code(row)` on `dac_pin` → waits (≤ `ack_timeout_ms`) for every `ack_pins`
input to read `code(row)` back → settles `settle_ms` → samples its own
channels → emits the frame with the row index in this module's channel.
On ack timeout it samples anyway — the node detects the misalignment by
comparing row tags across devices (followers emit their own, `-1` when they
saw nothing).

`max_code` exists for mixed rails: a 5 V conductor (e.g. an RA4M1) serving
3.3 V followers caps its codes at the followers' ADC ceiling. Default 65535
is correct for an all-3.3 V lattice.

## Contract placement

List this module **first** so the row tag is channel 0 of the frame — the
node-side `pressure_array` aligns the four device streams on it. `sample_hz`
is the row tick rate; full-lattice sweep rate = `sample_hz / rows`.

Counterpart: [`scan_follower`](../scan_follower/README.md).
