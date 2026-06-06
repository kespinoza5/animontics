# transport_serial (circuit_python module)

Marks the USB-serial uplink. **role:** transport (exactly one per contract).

The framing itself lives in the generic runtime (`templates/code.py.j2`), which
encodes the same `core/mcu_link.py` protocol-v1 frames as the AVR family — so the
node's `McuSerialDevice` decodes a CircuitPython board identically. This manifest
exists so the contract has a declared transport.
