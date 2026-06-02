try:
    from sensors.ir_xcvr.sensor import IrXcvrSensor
except ImportError:
    pass  # Linux-only hardware deps (fcntl) — skip gracefully on Windows

#: Hardware constraints and defaults for the fleet tool.
#: Connection details (actual LIRC device paths) live in the board's config.yaml.
METADATA = {
    "type": "ir_xcvr",
    "name": "IR Transceiver (TSOP38238 RX + TSAL6200 TX)",
    "description": (
        "38 kHz IR receiver and emitter via Linux LIRC. "
        "Receives and transmits NEC/NECX IR remote codes."
    ),
    "connection": {
        "supported": ["ir"],
        "defaults": {
            "rx_device": "/dev/lirc0",
            "tx_device": "/dev/lirc1",
        },
        # No hard constraints — device paths vary by board and kernel config.
        # Both rx_device and tx_device are optional; omit either to disable that half.
        "valid": {},
    },
    "data_keys": {
        "protocol": "str   — protocol name: NEC | NECX | NEC32 | RC5 | PROTO_N",
        "address":  "int   — decoded device address",
        "command":  "int   — decoded command byte",
        "scancode": "int   — (address << 8) | command for NEC family",
        "repeat":   "bool  — True when this is a held-key repeat frame",
    },
}

__all__ = ["IrXcvrSensor", "METADATA"]
