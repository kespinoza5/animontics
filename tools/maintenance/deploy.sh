#!/usr/bin/env bash
# deploy.sh — Legacy shell deploy script.
#
# SUPERSEDED BY: python -m tools.fleet.animon deploy <node-id>
#
# The Python fleet CLI (tools/fleet/) is now the primary deployment tool.
# It reads from config/animon.yaml, negotiates config changes with the board,
# validates against sensor METADATA, and handles packages more precisely.
#
# This script is kept as a fallback for environments without Python or where
# the fleet config (animon.yaml) is not yet set up.
#
# Usage:
#   ./tools/maintenance/deploy.sh <user@host> [config_file]
#
# Examples:
#   ./tools/maintenance/deploy.sh pi@192.168.1.y
#   ./tools/maintenance/deploy.sh pi@192.168.1.y config/rpi5.yaml
#
# Requirements on the target board:
#   - SSH key auth configured
#   - Python 3.11+ with pip
#   - Target install path: /opt/animontics

set -euo pipefail

TARGET="${1:-}"
CONFIG_FILE="${2:-config/config.yaml}"
REMOTE_PATH="/opt/animontics"
SERVICE_NAME="animontics-node"

if [[ -z "$TARGET" ]]; then
    echo "Usage: $0 <user@host> [config_file]"
    exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Config not found: $CONFIG_FILE"
    exit 1
fi

# Extract enabled sensor types from config
SENSOR_TYPES=$(python3 -c "
import yaml, sys
cfg = yaml.safe_load(open('$CONFIG_FILE'))
types = set()
for s in cfg.get('sensors', []):
    if s.get('enabled', True):
        types.add(s['type'])
print(' '.join(sorted(types)))
" 2>/dev/null || echo "")

echo "==> Deploying to $TARGET"
echo "    Config:  $CONFIG_FILE"
echo "    Sensors: ${SENSOR_TYPES:-none}"
echo ""

# Ensure remote directory exists
ssh "$TARGET" "sudo mkdir -p $REMOTE_PATH && sudo chown \$(whoami): $REMOTE_PATH"

# Core files always deployed
echo "--> Copying core/"
rsync -az --delete core/ "$TARGET:$REMOTE_PATH/core/"

echo "--> Copying node/"
rsync -az --delete node/ "$TARGET:$REMOTE_PATH/node/"

echo "--> Copying sensors/__init__.py"
rsync -az sensors/__init__.py "$TARGET:$REMOTE_PATH/sensors/__init__.py"

# Only copy sensor packages that are enabled in config
for sensor_type in $SENSOR_TYPES; do
    if [[ -d "sensors/$sensor_type" ]]; then
        echo "--> Copying sensors/$sensor_type/"
        rsync -az --delete "sensors/$sensor_type/" "$TARGET:$REMOTE_PATH/sensors/$sensor_type/"
    else
        echo "    WARNING: sensors/$sensor_type/ not found locally"
    fi
done

# Deploy config
echo "--> Copying config"
rsync -az "$CONFIG_FILE" "$TARGET:$REMOTE_PATH/config/config.yaml"

# Install/update Python dependencies
echo "--> Installing dependencies"
ssh "$TARGET" "cd $REMOTE_PATH && pip3 install -q -r requirements.txt" || true

# Restart service
echo "--> Restarting $SERVICE_NAME"
ssh "$TARGET" "sudo systemctl restart $SERVICE_NAME 2>/dev/null || echo '    (service not installed — start manually with: uvicorn node.app:app)'"

echo ""
echo "==> Done. Node at http://$TARGET:8080"
