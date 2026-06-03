# config/

Three-layer configuration for the animontics distributed system.

```
config/
├── animon.example.yaml    schema + placeholder template (in repo)
├── animon.yaml            your real fleet — IPs, SSH users (gitignored)
├── config.example.yaml    per-board wiring template (in repo)
├── config.yaml            active per-board config on a single board (gitignored)
└── nodes/                 dev-machine staging copies of board configs (gitignored)
    └── <node-id>.yaml
```

---

## Layer 1 — Hardware constraints (`sensors/<type>/__init__.py` METADATA)

Embedded in each sensor package — valid connection types, locked baud rates,
I2C address ranges, and defaults for fresh installs. The fleet tool reads METADATA
when adding a sensor to a board that has no existing wiring entry.

---

## Layer 2 — Board wiring reality (`config.yaml`)

Lives on the board at `<deploy_path>/config/config.yaml`. Controls what the node
agent loads and runs. **Gitignored** — each board holds its own copy.

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

Copy `config.example.yaml` and edit for the target board, or let the fleet tool
generate one:

```bash
# Probe the board and generate a config from discovered hardware
python -m tools.fleet.animon probe my_sbc_node

# Deploy (reads animon.yaml for desired state, negotiates wiring)
python -m tools.fleet.animon deploy my_sbc_node
```

Dev-machine staging copies live in `config/nodes/<node-id>.yaml` (gitignored).
Run `animon pull <node-id>` to fetch the live config from a board and store it there.

---

## Layer 3 — Fleet desired state (`animon.yaml`)

The whole-system topology: every node, what sensors it *should* carry (id + type
only — no wiring details), IPs, SSH access, and attached peripherals. Read by the
fleet tool to deploy, sync, and probe.

**Gitignored** — contains your real IPs and SSH usernames. Copy
`animon.example.yaml` → `animon.yaml` and fill in your values.

Update `animon.yaml` when:
- A new board joins the system
- A sensor moves to a different node
- IPs or SSH users change

---

## Connection Types

| Type | Description | Required fields |
|------|-------------|-----------------|
| `uart` | Hardware UART or USB-to-serial adapter | `port`, `baud_rate` |
| `usb_cdc` | USB CDC device (RP2040/SAMD running CircuitPython) | `port`, `baud_rate` |
| `i2c` | I2C bus | `bus`, `address` |

---

## Secrets

Secrets (WiFi passwords, API tokens) must never appear in any config file committed
to the repo. Store them in a gitignored `secrets.yaml` on each board, loaded via
the `ANIMONTICS_SECRETS` environment variable. SSH access uses key auth only — see
`tools/ssh/`.
