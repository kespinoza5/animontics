import time
import smbus2

I2C_BUS  = 1
ADS_ADDR = 0x48

# Config: AIN0 vs GND, ±4.096V range, single-shot, 128 SPS
CONFIG = [0xC3, 0x83]

def read_voltage(bus):
    bus.write_i2c_block_data(ADS_ADDR, 0x01, CONFIG)
    time.sleep(0.01)  # ~8ms conversion time at 128 SPS
    data = bus.read_i2c_block_data(ADS_ADDR, 0x00, 2)
    raw = (data[0] << 8) | data[1]
    if raw > 32767:
        raw -= 65536
    return raw * 4.096 / 32768

def voltage_to_distance(v, vcc=5.0):
    inches = v * 512 / vcc
    cm = inches * 2.54
    return inches, cm

bus = smbus2.SMBus(I2C_BUS)
print("Reading ADS1115 AIN0 — Ctrl+C to quit\n")

while True:
    try:
        v = read_voltage(bus)
        inches, cm = voltage_to_distance(v)
        print(f"  {v:.4f} V  →  {inches:.1f} in  ({cm:.1f} cm)")
        time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDone.")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(0.5)


