# pwm_out (arduino module)

PWM outputs — fans, LED brightness, unidirectional motor speed. **role:**
actuator · **claims:** pwm pins · **accepts:** `set_duty {channel, duty}`.

- `pwm_out.h/.cpp` — `PwmOut::set_duty(idx, 0..255)`; idle at 0 after setup.
- `decl/setup/cmd.j2` — instance, `pinMode`, and the `CMD_SET_DUTY` dispatch case
  (composed into the generated `onCommand`, fed by `transport_serial.poll`).

Driven from the node by the **effector** tier through the device — never a sensor.
