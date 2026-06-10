# ozzmaker_10dof — OzzMaker LTE-M GPS + 10DOF Sensor

Reads the three inertial/environmental chips on the
[OzzMaker SARA-R5 LTE-M GPS + 10DOF](https://ozzmaker.com/ozzmaker-sara-r5-lte-m-gps-10dof-overview/)
board over a single I2C bus.

| Chip | Default addr | Jumper | Alt addr | Measures |
|------|--------------|--------|----------|----------|
| LSM6DSL | 0x6A | JP8 (open) | 0x6B (solder-close) | 3-axis accel + 3-axis gyro |
| MMC5983MA | 0x30 | — (fixed) | — | 3-axis magnetometer |
| BMP388 | 0x77 | JP4 (closed) | 0x76 (cut trace) | barometric pressure + temperature |

The two address jumpers are physical board options, so the addresses are
**config**, not hard-coded — `imu_address` / `mag_address` / `baro_address` in the
sensor's `params` (defaults above). Reading the board config alone tells you where
each chip sits; you never have to dig into the driver.

## Wiring

Connect to Orange Pi I2C3 (SDA/SCL). The SARA-R5 modem and GPS on the same
physical board use UART5; see [`sara_r5_gnss`](../sara_r5_gnss/README.md) and
[`sara_r5_lte`](../sara_r5_lte/README.md) for those sensors.

## Board config (`config/boards/<node-id>.yaml`)

```yaml
sensors:
  - id: imu_1
    type: ozzmaker_10dof
    connection:
      type: i2c
      bus: 3
    params:
      imu_address:  0x6A   # LSM6DSL  — JP8 open (default); 0x6B if solder-closed
      mag_address:  0x30   # MMC5983MA — fixed
      baro_address: 0x77   # BMP388   — JP4 closed (default); 0x76 if trace cut
```

`params` is optional — omit it to use the defaults above. Set the relevant address
only if you've changed a jumper (JP8 for the IMU, JP4 for the barometer).

## Data keys

| Key | Type | Unit | Description |
|-----|------|------|-------------|
| `accel_x/y/z` | `float` | m/s² | Acceleration per axis (±2g range) |
| `gyro_x/y/z` | `float` | dps | Angular velocity per axis (125 dps range) |
| `imu_temp_c` | `float` | °C | LSM6DSL die temperature |
| `mag_x/y/z` | `float` | Gauss | Magnetic field per axis (±8G range) |
| `pressure_pa` | `float` | Pa | Atmospheric pressure |
| `temp_c` | `float` | °C | BMP388 temperature |
| `altitude_m` | `float` | m | ISA altitude estimate from pressure |

## Sample rates

- IMU (LSM6DSL): configured at 104 Hz internally; sensor loop reads at 50 Hz
- Magnetometer (MMC5983MA): one-shot per sensor loop iteration (~50 Hz)
- Barometer (BMP388): forced-mode once per second (reduces bus contention)

## Heading note

Raw magnetometer values are reported in the sensor frame. Heading computation
(tilt-compensated with accel + mag fusion) belongs in a Policy, not this sensor.
