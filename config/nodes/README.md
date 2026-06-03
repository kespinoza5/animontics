# config/nodes/ — node desired state

**These files are committed to the repo. They contain no secrets.**

One YAML file per node in the fleet. Each file describes what a node *should*
run — its sensor assignments, board type, role, and capabilities. No IPs, no
SSH users, no port paths or bus addresses.

## What belongs here

```yaml
# config/nodes/my_sbc_node.yaml
id:   my_sbc_node
type: raspberry_pi_5
role: vision
capabilities: [hailo_inference, coral_usb]
sensors:
  - id: lidar_front
    type: tf_mini
  - id: thermal_rear
    type: mlx90640
```

**What does NOT belong here:** IPs, SSH users, port paths, I2C bus/address,
baud rates. Those are wiring details — they go in `config/boards/<id>.yaml`
(dev-machine staging, gitignored) or the board's own `config.yaml`.

## When to edit

- Adding a sensor to a node → add `{id, type}` to the relevant file
- Removing a sensor → remove the entry (next `animon deploy` disables it)
- New node joining the fleet → create a new `<node-id>.yaml` here,
  add access details to `config/animon.yaml`

## Relationship to other config files

```
config/nodes/<id>.yaml     YOU ARE HERE — desired state (in repo)
         +
config/animon.yaml         access layer: IPs, SSH users (gitignored)
         │
         ▼  animon deploy
config/boards/<id>.yaml    wiring staging copy (gitignored, auto-updated)
         │
         ▼  rsync to board
<board>/config/config.yaml live board config (gitignored, on the board)
```
