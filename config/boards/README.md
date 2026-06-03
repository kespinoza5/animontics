# config/boards/ — board wiring staging copies

**`<node-id>.yaml` files are gitignored. Only `example.yaml` is tracked.**

One YAML file per board, named `<node-id>.yaml`. These are dev-machine staging
copies of each board's live `config.yaml` — same file format, just kept locally
so you can plan and diff without an active SSH connection.

See `example.yaml` for the full schema with all connection types documented.

## How files get here

```bash
# Fetch the live config from a board and store it here
animon pull my_sbc_node

# After a successful deploy, the staging copy is updated automatically
animon deploy my_sbc_node
```

## What's in each file

Full wiring details for all sensors on the board:

```yaml
node_id:   my_sbc_node
node_type: raspberry_pi_5
hostname:  animontics-node
network:
  host: "0.0.0.0"
  port: 8080
sensors:
  - id: lidar_front
    type: tf_mini
    enabled: true
    connection:
      type:      uart
      port:      /dev/ttyAMA0
      baud_rate: 115200
  - id: thermal_rear
    type: mlx90640
    enabled: true
    connection:
      type:    i2c
      bus:     1
      address: 0x33
```

## Relationship to other config files

`config/nodes/<id>.yaml` says *what* should run (desired state, in repo).
`config/boards/<id>.yaml` says *how* it's wired (physical reality, gitignored).
The fleet tool merges both — plus sensor METADATA defaults — when deploying.
