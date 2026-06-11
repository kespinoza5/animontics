# si5351 — clock generator (the audio clock tree's root)

An Si5351A on the pizero's 3.3 V I2C segment, programmed **once at boot** and
then only health-checked — a device with no data flow at all, which is exactly
why it's a device: it owns a shared physical resource (the clock tree) that
several other things depend on.

## Why it exists

The PCM1808 ADC needs an SCKI master clock (256×fs — 12.288 MHz for 48 kHz)
that SBC I2S headers don't provide. CLK0 supplies it; the PCM1808 runs in
**master mode** and derives BCLK/LRCLK from it, and that one clock domain is
shared across every audio endpoint (pizero capture + playback, the Broca
RP2040 research board, the FPGA fabric taps, the rpi5's reserved I2S tap).
Coherent capture/playback fleet-wide — the prerequisite for AEC later — is
solved here, at the physical layer.

## Behavior

- `params.clk0_hz` (default 12 288 000) → AN619 frequency plan: even integer
  output divider, fractional PLL feedback, <1 Hz error at audio rates
  (`plan_clock()` is pure and unit-tested).
- Health = register readback (`SYS_INIT` clear after programming).
- **Shutdown leaves the clock running.** A node restart must never collapse
  the fleet-wide clock domain; only the bus handle is released.

```yaml
devices:
  - id: clkgen_1
    kind: si5351
    bus: 1          # 3.3 V I2C segment (shared with the Pi; the 5 V ADS sits
    address: 0x60   #   behind the BSS138 shifter)
    params: {clk0_hz: 12288000}
```

```bash
pytest devices/si5351/ -v     # frequency plan + register encoding; no hardware
```
