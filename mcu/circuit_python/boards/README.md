# mcu/circuit_python/boards — per-board pin capability tables

One small YAML file per **board profile** (the `board:` a contract names —
`xiao_rp2040`, `feather_m4`, …). `load_platform()` merges these over the inline
`boards:` map in `platform.yaml`, so the family file stays family-level and the
pin tables live where they can grow.

`forge validate` (and therefore `build`) checks every pin a contract assigns
against these tables, via the module manifest's `claims` map
(`claims: {pins: pwm, dac_pin: dac, ack_pins: adc}` — param name → capability
kind). A pin that lacks the capability, a kind with no table, and any pin
claimed twice all fail validation on the dev machine.

## File schema

```yaml
board: seeed_xiao_rp2040     # CircuitPython board module name (deploy target)
logic_v: 3.3                 # logic level — future voltage-domain checks
pins:
  gpio:    [D0, D1, …]       # flat capabilities: a plain pin list
  adc:     [A0, …]
  dac:     [A0]              # scarce — the scan handshake depends on these
  pwm:     [D1, …]
  countio: [D1, D7, …]       # RP2040: PWM B channel = odd GP numbers ONLY
  uart:    {tx: [D6], rx: [D7]}        # bus protocols are ROLE-STRUCTURED:
  i2c:     {scl: [D5], sda: [D4]}      # TX≠RX, BCLK≠DIN. Claims reference a
  spi:     {sck: [D8], mosi: [D10],    # role with a dotted kind, e.g.
            miso: [D9], cs: [...]}     # claims: {tx_pin: uart.tx}
```

The capability vocabulary is **the CircuitPython peripheral classes** —
`gpio` (digitalio), `adc` (AnalogIn), `dac` (AnalogOut), `pwm` (pwmio),
`countio`, plus role-structured bus protocols. Don't invent kinds; if a new
module needs one, it's because a new peripheral class is in play.

## Authoring and verifying

Tables are authored from the datasheet / CircuitPython docs; entries that
haven't been confirmed on silicon carry a `# VERIFY` comment. The source of
truth is the chip itself: `mcu/circuit_python/validate_pins.py` (bench script)
probes a live board over CIRCUITPY and prints its table in this exact format —
verifying a board is a diff, not a transcription. A board profile with no file
here simply gets no capability checking (claims error with "no pin table"
only when a contract actually claims that kind).
