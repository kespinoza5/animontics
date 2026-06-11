# speaker — ALSA playback + amp gate (MAX98357A)

The mouth: a MAX98357A I2S class-D amp driving the ADA1313 3" 8 Ω driver,
hanging on the **same full-duplex I2S bus** the PCM1808 captures on (see
`sensors/audio_in` for the clock-domain rationale — shared BCLK/LRCLK means
speech out is sample-coherent with hearing in).

## Lanes

- **stream** (`WS /effectors/<id>/stream`): raw interleaved **S16_LE** fed to
  an `aplay` raw pipe — spawned lazily on first chunk, respawned on a broken
  pipe, byte-symmetric with what `audio_in` captures (loopback tests are
  trivial).
- **request** (`POST /effectors/<id>` `{"on": bool}`): the amp's **SD pin**
  via a `core/gpio.py` line (`params.sd_line`) — gating the amp is a GPIO,
  not a relay; it costs nothing and kills idle hiss. Enabled at startup.

## Hardware notes

- The MAX98357A can push ~1.8 W into 8 Ω; the ADA1313 is rated 1 W — the
  **gain strap is the hardware ceiling**, set it conservatively. Software owns
  what to say; the strap owns how loud it can possibly be.
- No MCLK needed (the amp is always an I2S slave), so it follows the tree
  wherever its DIN comes from. The Broca's-area RP2040 (clock-slave I2S TX,
  research track) can take over the DIN later by moving one wire and this
  effector's config — the seam is deliberate.

```yaml
effectors:
  - id: voice
    type: speaker
    params:
      alsa_device: "hw:0,0"
      sd_line: {backend: libgpiod, chip: gpiochip0, line: 17}   # VERIFY pin
```

```bash
pytest effectors/speaker/ -v   # SD gate, stream accounting; no hardware
```
