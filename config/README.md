# config

Two-layer configuration for the animontics distributed system.

## Layer 1 — Per-Board (`config.yaml`)

Lives on the board. Controls what the node agent loads and runs. **Gitignored** — each board holds its own copy so the repo doesn't accumulate per-device files.

```yaml
node_id:   my_sbc_node
node_type: orangepi_zero2
hostname:  animontics-node

network:
  host: "0.0.0.0"
  port: 8080

sensors:
  - id: lidar_front
    type: tf_mini          # must match a @register key in sensors/
    enabled: true
    connection:
      type:      uart
      port:      /dev/ttyAMA0
      baud_rate: 115200
```

Copy `config.example.yaml` to `config.yaml` and edit for the target board. Deploy it with:

```bash
./tools/maintenance/deploy.sh pi@<board-ip>
```

## Layer 2 — Fleet Map (`fleet.yaml`)

Lives in the repo. Documents the whole distributed system: every node, what sensors it carries, and how it connects. Not read by any server at runtime — used by developers and future fleet management tooling.

Update `fleet.yaml` when:
- A new board is added to the system
- A sensor is moved to a different node
- IP addresses or hostnames change

## Files

| File | Purpose |
|------|---------|
| `config.example.yaml` | Full documented template — copy this to `config.yaml` |
| `config.yaml` | Active per-board config — **gitignored**, do not commit |
| `fleet.yaml` | Whole-system topology map |

## Connection Types

| Type | Description | Required fields |
|------|-------------|-----------------|
| `uart` | Hardware UART or USB-to-serial adapter | `port`, `baud_rate` |
| `usb_cdc` | USB CDC device (RP2040/SAMD running CircuitPython) | `port`, `baud_rate` |
| `i2c` | I2C bus | `bus`, `address` |
