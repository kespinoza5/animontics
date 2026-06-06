# transport_serial (arduino module)

The uplink transport — frames the sample vector and drains inbound commands.
**role:** transport (exactly one per contract) · **claims:** uart (D0/D1).

- `transport_serial.h/.cpp` — `send(frame, count, seq)` writes a protocol-v1 frame;
  `poll(handler)` decodes inbound `AC` command frames and dispatches them.
- `decl/setup/send/poll.j2` — instance, `begin(baud)`, `send(...)`, and
  `poll(onCommand)` composed into `main.ino`.

The on-wire layout MUST match [`core/mcu_link.py`](../../../../core/mcu_link.py)
(the node decodes with it) — change one, bump `PROTOCOL_VERSION` in both.
