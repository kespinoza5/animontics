# mcu/arduino/boards/ — per-board capability tables

One small YAML per board profile, merged **over** the inline `boards:` map in
[`../platform.yaml`](../platform.yaml) by `forge` (`tools/forge/contract.py`
`load_platform`). A board file holds what would bloat platform.yaml: the
`fqbn`, pin-capability tables (`adc`/`pwm`/`gpio`/`countio`/`uart`/…), logic
voltage, and `adc_bits`. `forge validate` checks every module's claimed pins
against these tables.

Use a board file when a board's pin map differs from the family defaults — the
AVR Nano/Uno are simple enough to live inline in `platform.yaml`; the Renesas
RA4M1 needs its own table.

| Profile | Chip / board | FQBN |
|---------|--------------|------|
| `ra4m1_zero` | Renesas RA4M1 (Waveshare RA4M1-Zero, UNO R4 core) | `arduino:renesas_uno:minima` |

## `ra4m1_zero`

The Waveshare RA4M1-Zero flashes with the **UNO R4 Minima** FQBN, so the pin
tokens are the Minima Arduino names (`D0–D13`, `A0–A5`) the composed sketch
compiles against — **not** the Waveshare silk. Map the Waveshare pads to these
Arduino pins against the **schematic** before authoring a contract:
<https://files.waveshare.com/wiki/RA4M1-Zero/RA4M1-zero-schematic.pdf>.

Notes:

- **Serial1 = D0(RX)/D1(TX)** carries the MB1010 digital lane (through the 2N3904
  inverter). The SBC uplink is native **USB CDC** (`Serial`), which claims no
  GPIO, so D0/D1 stay free for `serial_sonar`.
- **14-bit ADC**: `analog_in` raises the resolution from the 10-bit default and
  uses **AREF=external** (AREF tied to 5 V) for the ratiometric MB1010 AN +
  ACS712 lanes.
- All tables are marked **VERIFY** — confirmed against the RA4M1/UNO R4 core but
  not yet checked against the Waveshare board on hardware.
