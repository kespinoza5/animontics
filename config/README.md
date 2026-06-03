# config/

Four-layer configuration for the animontics distributed system.

```
config/
├── nodes/                      ← IN REPO — node desired state (no secrets)
│   ├── my_other_node.yaml
│   ├── my_pizero_node.yaml
│   ├── my_sbc_node.yaml
│   ├── my_hub_node.yaml
│   └── my_inference_node.yaml
├── animon.example.yaml         ← IN REPO — access layer template
├── animon.yaml                 ← GITIGNORED — real IPs, SSH users
├── boards/                     ← GITIGNORED — dev-machine wiring staging copies
│   └── <node-id>.yaml
├── config.example.yaml         ← IN REPO — per-board wiring template
└── config.yaml                 ← GITIGNORED — active per-board config on board
```

---

## Layer 1 — Node desired state (`config/nodes/<id>.yaml`)

**In repo. No secrets.**

One file per node. Describes what a node *should* run: sensors (id + type only),
board type, role, capabilities. Written by humans when designing the system.
No IPs, no ports, no bus addresses.

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

Update this file when:
- A sensor is added to or removed from a node
- A new node joins the fleet (create a new file)

---

## Layer 2 — Fleet access (`config/animon.yaml`)

**Gitignored. Contains real IPs and SSH users.**

Copy `animon.example.yaml` → `animon.yaml` and fill in your values. The fleet
tool reads this to know how to reach each board. Node IDs must match the `id`
fields in `config/nodes/`.

```yaml
# config/animon.yaml (gitignored)
defaults:
  ssh_user: pi
nodes:
  my_sbc_node:
    ip:       192.168.1.x
    ssh_user: myuser
  my_pizero_node:
    wifi_ip: 192.168.1.x
    connection:
      via: usb_gadget
      host: my_other_node
      usb_ip: 192.168.8.x
```

---

## Layer 3 — Board wiring (`config/boards/<id>.yaml`)

**Gitignored. Dev-machine staging copies of each board's `config.yaml`.**

Full wiring details: UART port paths, I2C bus/address, baud rates, enabled flags.
Same schema as the board's `config.yaml`. Populated by `animon pull <node-id>`;
updated automatically after `animon deploy`. Allows offline `--dry-run` planning.

Run `animon pull <node-id>` to fetch the live config from a board and store it here.

---

## Layer 4 — Hardware constraints (`sensors/<type>/__init__.py` METADATA)

**In repo, in each sensor package.**

Valid connection types, locked baud rates, I2C address ranges, and defaults for
new sensors. The fleet tool reads METADATA when a sensor appears in `nodes/` but
has no wiring entry in `boards/` — it bootstraps from these defaults.

---

## Connection Types

| Type | Description | Required wiring fields |
|------|-------------|------------------------|
| `uart` | Hardware UART or USB-to-serial | `port`, `baud_rate` |
| `usb_cdc` | USB CDC (RP2040/SAMD CircuitPython) | `port`, `baud_rate` |
| `i2c` | I2C bus | `bus`, `address` |

---

## Secrets

Secrets (WiFi passwords, API tokens) must never appear in any committed file.
Store them in a gitignored `secrets.yaml` per board, loaded via the
`ANIMONTICS_SECRETS` environment variable. SSH access uses key auth only.
