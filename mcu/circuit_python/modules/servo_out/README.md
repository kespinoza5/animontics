# servo_out (circuit_python module)

Hobby-servo pulse outputs via `pwmio.PWMOut` at 50 Hz (`freq_hz`). **role:**
actuator · **accepts:** `set_us {channel, us}` (`CMD_SET_US = 2` in
`core/mcu_link.py`) — pulse width in microseconds, mapped to
`duty_cycle = us * freq_hz * 65535 // 1_000_000`.

`min_us`/`max_us` are **absolute safety clamps** (default 500–2500) so a
corrupt or out-of-range command can't command an impossible pulse. They are
*not* per-servo soft limits: angle→µs mapping, travel limits, and trim live in
the node's `effectors/servo` tier, which is the only thing that should be
sending these commands. Firmware moves microseconds; Python owns meaning.

Distinct from `pwm_out` (duty-cycle loads like fans): a servo channel is
microsecond-pulse semantics at a fixed 50 Hz frame rate, and the two modules
can coexist on one board (separate pins, separate frequencies).

Power note: servos are powered from their own V+ rail (common ground), never
from the MCU. Stall currents (e.g. DS3218: ~2.5–3 A each) size the rail —
see the `power_rail` effector for rail gating.
