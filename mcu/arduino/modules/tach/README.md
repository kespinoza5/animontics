# tach (arduino module)

Captures fan **tach (FG)** RPM via pin-change interrupts on the RA4M1 (and any
AVR/Arduino board with interrupt-capable pins). **role:** sensor · **provides:**
one frame channel per FG pin (RPM as signed int16, wire order = pin order).
**config:** `pulses_per_rev` (default 2), `sample_hz` (default 4).

Each FG pin is driven `INPUT_PULLUP` (FG is open-collector) and falling edges are
counted in an ISR. Each sample period `read()` computes
`rpm = edges · 60000 / (pulses_per_rev · dt_ms)`, clears the counter, and writes
it into the uplink frame. Because these are 4-pin fans (V+/GND always powered),
FG is valid at **any** PWM duty — so one board can drive the fans (`pwm_out`) and
read their RPM (`tach`) at once. Node-side, the [`fan_tach`](../../../../sensors/fan_tach)
sensor labels the channels as RPM.

`claims: countio` — each FG pin must be interrupt-capable on the board (see the
board profile's `countio` table). The interrupt bank is a fixed module-global
(`TACH_MAX = 6` total channels across all `tach` instances), since
`attachInterrupt()` takes a bare function pointer.

This is the AVR/Arduino counterpart of the CircuitPython
[`tach`](../../../circuit_python/modules/tach) module (which uses
`countio.Counter`); both stream RPM in the same `core/mcu_link.py` frame.
