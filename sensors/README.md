# sensors

Sensor plugin packages. Each subdirectory is an independent git repository and a self-contained Python package.

## Plugin System

`sensors/__init__.py` uses `pkgutil.iter_modules` to auto-discover every package directory present on disk at import time. Each discovered package is imported, which triggers its `@register("type")` decorator and adds it to the global registry.

This means:
- **No static imports** — adding a sensor to a board is `scp` + restart, no code changes
- **Only present code is loaded** — boards carry only the packages they need
- **Missing hardware dependencies are skipped** — an `ImportError` (e.g. `smbus2` not installed) logs at DEBUG and continues; the board doesn't crash

## Available Sensor Packages

| Package | Sensor | Interface | Data |
|---------|--------|-----------|------|
| [`tf_mini/`](tf_mini/README.md) | Benewake TF Mini Plus LiDAR | UART | `distance_mm`, `strength`, `temp_c` |
| [`lv_maxsonar/`](lv_maxsonar/README.md) | MaxBotix LV-MaxSonar-EZ | UART | `distance_mm` |
| [`vl53l1x/`](vl53l1x/README.md) | ST VL53L1X time-of-flight | I2C | `distance_mm` |
| [`mlx90640/`](mlx90640/README.md) | Melexis MLX90640 32×24 thermal | I2C | `pixels[]`, `min_temp`, `max_temp` |

## Adding a New Sensor

See [CONTRIBUTING.md](../CONTRIBUTING.md). The short version:

```
sensors/
└── my_sensor/
    ├── __init__.py    ← imports MySensor, triggers @register
    ├── driver.py      ← pure hardware protocol, no HTTP or threading
    ├── sensor.py      ← @register("my_sensor") class MySensor(SensorBase)
    ├── viewer.html    ← desktop diagnostic viewer
    └── README.md
```

No changes needed anywhere else. Deploy just this directory to boards that need it.

## Deploying a Sensor Package

```bash
# deploy.sh reads config.yaml and copies only the needed packages
./tools/maintenance/deploy.sh pi@192.168.1.x

# Manual copy of a single package
rsync -az sensors/tf_mini/ pi@192.168.1.x:/opt/animontics/sensors/tf_mini/
```
