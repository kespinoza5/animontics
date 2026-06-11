# SPDX-FileCopyrightText: 2021 Melissa LeBlanc-Williams for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""Pin definitions for the Orange Pi Zero 2 (Allwinner H616).

26-pin header physical-to-SoC mapping:
 Pin  1: 3.3V       Pin  2: 5V
 Pin  3: PH5 (I2C3_SDA / TWI3_SDA)
 Pin  4: 5V
 Pin  5: PH4 (I2C3_SCL / TWI3_SCK)
 Pin  6: GND
 Pin  7: PC9
 Pin  8: PH2 (UART5_TX)
 Pin  9: GND
 Pin 10: PH3 (UART5_RX)
 Pin 11: PC5
 Pin 12: PC6
 Pin 13: PC7
 Pin 14: GND
 Pin 15: PC8
 Pin 16: PC10
 Pin 17: 3.3V
 Pin 18: PC11
 Pin 19: PH7 (SPI1_MOSI)
 Pin 20: GND
 Pin 21: PH8 (SPI1_MISO)
 Pin 22: PC13
 Pin 23: PH6 (SPI1_CLK)
 Pin 24: PH9 (SPI1_CS0)
 Pin 25: GND
 Pin 26: PC14
"""

from adafruit_blinka.microcontroller.allwinner.h616 import pin

# ── Physical header pins (D-numbered, RPi-style) ─────────────────────────────
D3  = pin.PH5   # physical  3
D5  = pin.PH4   # physical  5
D7  = pin.PC9   # physical  7
D8  = pin.PH2   # physical  8  (UART5_TX)
D10 = pin.PH3   # physical 10  (UART5_RX)
D11 = pin.PC5   # physical 11
D12 = pin.PC6   # physical 12
D13 = pin.PC7   # physical 13
D15 = pin.PC8   # physical 15
D16 = pin.PC10  # physical 16
D18 = pin.PC11  # physical 18
D19 = pin.PH7   # physical 19  (SPI1_MOSI)
D21 = pin.PH8   # physical 21  (SPI1_MISO)
D22 = pin.PC13  # physical 22
D23 = pin.PH6   # physical 23  (SPI1_CLK)
D24 = pin.PH9   # physical 24  (SPI1_CS0)
D26 = pin.PC14  # physical 26

# ── I2C ───────────────────────────────────────────────────────────────────────
# I2C3 (TWI3) on PH4/PH5 — the primary header I2C bus
SDA  = pin.PH5
SCL  = pin.PH4

# ── SPI ───────────────────────────────────────────────────────────────────────
# SPI1 on PH6–PH9
MOSI = pin.PH7
MISO = pin.PH8
SCLK = pin.PH6
SCK  = SCLK
CE0  = pin.PH9

# ── UART ─────────────────────────────────────────────────────────────────────
# UART5 on PH2/PH3
TX   = pin.PH2
RX   = pin.PH3
UART5_TX = pin.PH2
UART5_RX = pin.PH3

# ── Named aliases (SoC pin names) ─────────────────────────────────────────────
PC5  = pin.PC5
PC6  = pin.PC6
PC7  = pin.PC7
PC8  = pin.PC8
PC9  = pin.PC9
PC10 = pin.PC10
PC11 = pin.PC11
PC13 = pin.PC13
PC14 = pin.PC14
PH2  = pin.PH2
PH3  = pin.PH3
PH4  = pin.PH4
PH5  = pin.PH5
PH6  = pin.PH6
PH7  = pin.PH7
PH8  = pin.PH8
PH9  = pin.PH9from adafruit_blinka.microcontroller.allwinner.h616 import pin

# Basic GPIO mapping for Orange Pi Zero2 26‑pin header
# These names match the Raspberry Pi‑style names Blinka expects.

D3 = pin.PA6     # Physical pin 7
D5 = pin.PA7     # Physical pin 29
D7 = pin.PA8     # Physical pin 31
D8 = pin.PA9     # Physical pin 33
D10 = pin.PA10   # Physical pin 35

# I2C
SDA = pin.PA12   # Physical pin 3
SCL = pin.PA11   # Physical pin 5

# SPI (if enabled)
SCLK = pin.PC2
MOSI = pin.PC0
MISO = pin.PC1
CS0 = pin.PC3
