# tools/board

Scripts for verifying and configuring hardware interfaces on a board.

## Tools

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
