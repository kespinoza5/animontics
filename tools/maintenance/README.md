# tools/maintenance

Scripts for deploying and updating animontics on remote boards.

## Tools

### `deploy.sh`

Deploys animontics to a target board over SSH + rsync. Reads the board's `config.yaml` to determine which sensor packages are needed, then copies only those packages (plus `core/`, `node/`, `config/`) — boards never receive code for sensors they don't use.

```bash
# Deploy using the local config/config.yaml
python -m tools.fleet.animon deploy my_sbc_node

# Preview what will change without touching the board
python -m tools.fleet.animon deploy my_sbc_node --dry-run
```

**What it does:**
1. Parses `config.yaml` to extract enabled sensor types
2. `rsync` copies `core/`, `node/`, `sensors/__init__.py`
3. `rsync` copies only the sensor packages listed in config
4. Copies the config file to `/opt/animontics/config/config.yaml` on the board
5. Runs `pip3 install -r requirements.txt` on the board
6. Restarts the `animontics-node` systemd service

**Prerequisites on the target board:**
- SSH key auth configured (no password prompt)
- Python 3.11+
- Target install path: `/opt/animontics`

**Prerequisites locally:**
- `rsync` available
- A valid `config.yaml` for the target board
