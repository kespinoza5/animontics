# ads1115 — ADS1115 ADC device

A 4-channel 16-bit ADS1115 ADC on the SBC's own I2C bus. **Pull model:** a single
muxed converter shared by several scalar sensors; `read_channel(ch, gain)`
serializes a single-shot conversion and returns signed counts. Used by
`analog_in` (heterogeneous scalars) and the `pressure_array` surface.

```yaml
# config/boards/<node>.yaml
devices:
  - id: head_adc
    kind: ads1115
    bus: 1
    address: 0x48      # ADDR pin → GND=0x48, VDD=0x49, SDA=0x4A, SCL=0x4B
```

Calibration and units live in the **sensor** that reads the channel, never here —
the device only moves raw counts.
