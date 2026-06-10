# mcu_serial — MCU serial link device

An MCU on a serial link (USB CDC or hardware UART). **Push model:** a read pump
decodes [`core/mcu_link.py`](../../core/mcu_link.py) frames and fans each one to
subscriber callbacks (array sensors like `mq_array`, `fan_tach`); effectors send
command frames back over the same link via `send_command()`.

```yaml
# config/boards/<node>.yaml
devices:
  - id: larduino
    kind: mcu_serial
    port: /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0   # by-id survives re-enumeration
    baud: 115200
```

Built/flashed with [`tools/forge`](../../tools/forge) from `config/mcus/<id>.yaml`.
Sensors bind by listing `devices: [larduino]`; effectors bind via
`backend: {device: larduino}`.
