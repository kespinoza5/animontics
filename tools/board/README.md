# tools/board

Scripts for verifying and configuring hardware interfaces on a board. Run these
**on the board itself** (the setup scripts need root). They are Raspberry Pi OS
only — Orange Pi / Armbian boards use `armbian-config` for the same toggles.

## Tools

### Interface setup — `setup_i2c.sh`, `setup_uart.sh`, `setup_spi.sh`, `setup_i2s.sh`

Enable a hardware bus and create its device nodes by editing the firmware
`config.txt` (`/boot/firmware/config.txt` on Bookworm, `/boot/config.txt` on
older releases). All four are **idempotent** — re-running never duplicates a
line — and make a one-time `.anim.bak` backup the first time they touch a file.
A reboot is required for changes to take effect.

```bash
sudo ./setup_i2c.sh                      # enable I2C at 100 kHz
sudo ./setup_i2c.sh --baudrate 400000    # fast-mode I2C
sudo ./setup_uart.sh                     # enable UART + free it from the login console
sudo ./setup_spi.sh                      # enable SPI (/dev/spidev*)
sudo ./setup_i2s.sh                      # enable I2S audio
sudo ./setup_i2s.sh --overlay googlevoicehat-soundcard   # + a device overlay
```

`setup_uart.sh` additionally strips the serial console from `cmdline.txt` and
disables the `serial-getty` login service, so UART sensors (TF Mini,
LV-MaxSonar) get a clean port.

Shared logic (config-file editing, root check, reboot notice) lives in
`lib_config.sh`, which the four scripts source — it is not run directly.

After a reboot, confirm the interfaces with `verify_comms.sh`.

### `verify_comms.sh`

Scans all hardware communication interfaces and prints what's present. Run this after initial board setup to confirm sensors are wired and visible before starting the node agent.

```bash
# On the board directly
./verify_comms.sh

# From your development machine (via fleet CLI)
python -m tools.fleet.animon probe my_sbc_node
```

**Output includes:**
- All I2C buses (`/dev/i2c-*`) with `i2cdetect` scan results
- Hardware UART devices (`/dev/ttyAMA*`, `/dev/ttyS*`)
- USB CDC / USB serial devices (`/dev/ttyACM*`, `/dev/ttyUSB*`) with VID/PID and product name
- Full `lsusb` USB device list

**Requirements:** `i2c-tools` for I2C scanning (`sudo apt install i2c-tools`)

**Expected output example:**
```
========================================
  Animontics — Hardware Comms Verify
========================================

── I2C Buses ────────────────────────────

  /dev/i2c-3:
       0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
  00:  -- -- -- -- -- -- -- -- -- -- -- -- -- --
  ...
  30: -- -- -- 33 -- -- -- -- -- -- -- -- -- -- -- --
  ...

── UART / Serial Devices ────────────────
  /dev/ttyAMA0

── USB CDC / Serial (ttyACM*, ttyUSB*) ──
  /dev/ttyACM0  (2e8a:0005)  Pico

── All USB Devices ──────────────────────
  Bus 001 Device 002: ID 2e8a:0005 Raspberry Pi Pico
```
