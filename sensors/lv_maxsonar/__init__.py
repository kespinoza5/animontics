try:
    from sensors.lv_maxsonar.sensor import (
        LVMaxSonar,
        LVMaxSonarArray,
        LVMaxSonarSensor,
    )
except ImportError:
    pass  # pyserial not available on dev machines — skip gracefully

#: Hardware constraints and defaults for the fleet tool.
#: Connection details (actual port/baud used) live in the board's config.yaml.
#:
#: Two deployment modes (dispatched by config shape):
#:   - direct UART  — `connection:` set; the SBC reads R<NNN> itself. The MB1010
#:     TX is inverted (RS232 logic, idles LOW), so it needs a hardware inverter
#:     (74HC14 / 2N3904) on the TX line before the SBC RX.
#:   - device-fed   — `devices:`/`channels:` set; an MCU (e.g. the LR4Z RA4M1)
#:     reads the sonar and streams it. Each channel's calibration is
#:     {type: maxsonar, mode: inches|counts[, scale]} → distance_mm.
METADATA = {
    "type": "lv_maxsonar",
    "name": "MaxBotix LV-MaxSonar-EZ",
    "description": "Ultrasonic distance sensor, range up to 6.45 m. Direct UART "
                   "(needs a hardware TX inverter) or device-fed via an MCU "
                   "(inches/counts → distance_mm).",
    "connection": {
        "supported": ["uart", "usb_cdc"],   # device-fed mode omits connection
        "defaults": {
            "baud_rate": 9600,
        },
        "valid": {
            # baud_rate is fixed in hardware
            "baud_rate": [9600],
        },
    },
    "data_keys": {
        "distance_mm": "int  — measured distance in millimetres (whole-inch source "
                       "→ quantized to ~25 mm)",
        "strength":    "None — not provided by this sensor",
        "temp_c":      "None — not provided by this sensor",
        "raw":         "dict[str,int] — device-fed mode: raw channel value(s) "
                       "(inches or ADC counts) keyed by signal",
        "seq":         "int — device-fed mode: most recent device frame sequence",
    },
}

__all__ = ["LVMaxSonar", "LVMaxSonarSensor", "LVMaxSonarArray", "METADATA"]
