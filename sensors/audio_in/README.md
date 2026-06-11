# audio_in — stereo capture (PCM1808 on the shared clock tree)

Audition: two FA-MT01 microphones through a PCM1808 24-bit stereo ADC into the
pizero's I2S, captured as S16_LE and served on both lanes.

## The clock domain (why this wiring)

The PCM1808 needs an SCKI master clock that SBC I2S headers don't provide, and
in **slave** mode its SCKI must be synchronized to LRCK — which an external
clock gen can't guarantee. So the working configuration is:

```
SI5351 CLK0 (12.288 MHz = 256 × 48 kHz)  →  PCM1808 SCKI, MASTER mode
PCM1808  →  shared MCLK/BCLK/LRCLK tree  →  pizero I2S (SLAVE, full duplex)
                                          →  Broca RP2040, FPGA taps, rpi5 (reserved)
PCM1808 DOUT → PCM_DIN (GPIO20);  PCM_DOUT (GPIO21) → MAX98357A DIN
```

One clock domain, fleet-wide: capture here and playback (`effectors/speaker`)
are sample-coherent — the prerequisite for echo cancellation later — and any
board slaving to the tree hears the same clock. I2S claims GPIO18–21, which is
why the ear servos live on GPIO12/13 (see `effectors/servo`).

## Lanes

- **Binary frame lane** (`WS /sensors/<id>/frames`): every captured block —
  header `<IHHI>` = (frame_id, channels, bits, rate), payload raw interleaved
  S16_LE. ~2.3 Mbps at 48 kHz stereo; the network lane to the inference hub
  carries it comfortably (measured before adding wires — the rpi5's I2S tap
  stays in reserve).
- **JSON lane**: per-channel `{rms, peak, dbfs}` summaries at `params.json_hz`
  (default 5/s) for status, viewers, and policies (a sound-level reflex is one
  `threshold` policy away).

Connectionless: the I2S bus is OS plumbing (`tools/board/setup_i2s.sh`
overlay), so config carries only `params` — alsa_device, sample_rate,
channels, block_ms. Capture prefers `pyalsaaudio`, falls back to an `arecord`
raw pipe, and degrades to cleanly-unhealthy where neither exists.

## Tests

```bash
pytest sensors/audio_in/ -v   # PCM block math, channel independence; no hardware
```
