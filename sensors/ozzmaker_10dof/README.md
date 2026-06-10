# ozzmaker_10dof — OzzMaker LTE-M GPS + 10DOF Sensor

Reads the three inertial/environmental chips on the
[OzzMaker LTE-M GPS + 10DOF](https://ozzmaker.com/product/lte-m-gps-10dof/) board
over a single I2C bus.

| Chip | Address | Measures |
|------|---------|----------|
| LSM6DSL | 0x6A | 3-axis accel + 3-axis gyro |
| MMC5983MA | 0x30 | 3-axis magnetometer |
| BMP388 | 0x77 | Barometric pressure + temperature |

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
```

No address is needed — all three chip addresses are fixed silicon.

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
