# tach (circuit_python module)

Captures fan **tach (FG)** RPM via CircuitPython `countio.Counter` (hardware edge
counting on RP2040/RP2350). **role:** sensor · **provides:** one frame channel per
FG pin (RPM as signed int16). **config:** `pulses_per_rev` (default 2).

Each tick the runtime reads each counter's delta and computes
`rpm = edges · 60 / pulses_per_rev / period`, streaming it in the same uplink
frame as any other sensor channel. Because these are 4-pin fans (V+/GND always
powered), FG is valid at **any** PWM duty — so a board can drive the fans (`pwm_out`)
and read their RPM (`tach`) at once. Node-side, the `fan_tach` sensor labels the
channels as RPM.

`pins` are the FG GPIOs (board attr names). FG is open-collector — needs a pull-up,
and goes through the level shifter on a 5 V fan.
