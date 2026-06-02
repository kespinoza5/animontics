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

Copy `config.example.yaml` to `config.yaml` and edit for the target board, or let the fleet tool generate one:

```bash
# Probe the board's hardware and generate a config
python tools/fleet/animon.py probe my_sbc_node

# Deploy using animon.yaml as the desired state
python tools/fleet/animon.py deploy my_sbc_node
```

## Layer 2 — Fleet Topology (`animon.yaml`)

Lives in the repo. The **desired state** for the whole distributed system: every node, what sensors it carries (by id and type — no wiring details), and how nodes connect. Read by the fleet tool to deploy, sync, and probe.

Update `animon.yaml` when:
- A new board is added to the system
- A sensor is moved to a different node
- IP addresses or hostnames change

## Files

| File | Purpose |
|------|---------|
| `config.example.yaml` | Full documented template — copy this to `config.yaml` |
| `config.yaml` | Active per-board config — **gitignored**, do not commit |
| `animon.yaml` | Whole-system topology and desired state |

## Connection Types

| Type | Description | Required fields |
|------|-------------|-----------------|
| `uart` | Hardware UART or USB-to-serial adapter | `port`, `baud_rate` |
| `usb_cdc` | USB CDC device (RP2040/SAMD running CircuitPython) | `port`, `baud_rate` |
| `i2c` | I2C bus | `bus`, `address` |

## Secrets

Secrets (WiFi passwords, API tokens) must never appear in `config.yaml` or `animon.yaml`.
Store them in a gitignored `secrets.yaml` on each board and reference via the
`ANIMONTICS_SECRETS` environment variable. SSH access uses key auth — see `tools/ssh/`.
