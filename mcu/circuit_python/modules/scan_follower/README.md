# scan_follower (circuit_python module)

The **follower** half of a multi-MCU scanned analog matrix (see
[`matrix_scan`](../matrix_scan/README.md) for the full handshake spec).
**role:** sensor · **provides:** `channels: 1` (the decoded row index, or
**-1** on watch timeout).

Per tick the follower: watches `watch_pin` (AnalogIn) for a **new** valid row
level from the conductor's DAC → settles `settle_ms` → samples its own
channels for that row → **acks** by echoing the level on `ack_pin` (its own
DAC) → emits the frame with the decoded row in this module's channel.

Acking *after* sampling is the contract: when the conductor has all acks, it
knows every follower sampled the energized row, and only then samples and
advances.

If no new level arrives within `watch_timeout_ms`, the follower emits a frame
anyway with row = **-1** — a dead or disconnected conductor degrades to a
visible sentinel in the data stream, never to silence.

`rows` and `max_code` must match the conductor's contract exactly (manual
sync today; cross-contract validation is a recorded TODO). List this module
**first** in the contract so the row tag is channel 0.
