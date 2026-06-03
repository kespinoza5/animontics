#!/usr/bin/env bash
# distribute_keys.sh — Push your fleet public key to the boards (run on dev machine).
#
# Reads node access details from config/animon.yaml and runs ssh-copy-id against
# each one, so afterwards the animon CLI can connect with key auth (BatchMode).
# ssh-copy-id will prompt for each board's password ONCE — that initial password
# is never stored and never passed on the command line.
#
# Usage:
#   ./tools/ssh/distribute_keys.sh                          # all nodes in animon.yaml
#   ./tools/ssh/distribute_keys.sh my_sbc_node              # one node
#   ./tools/ssh/distribute_keys.sh --identity ~/.ssh/animontics_ed25519.pub
#   ./tools/ssh/distribute_keys.sh --access path/to/animon.yaml
#   ./tools/ssh/distribute_keys.sh --dry-run                # print targets, copy nothing
#
# Prerequisite: generate a key first with ./tools/ssh/gen_keys.sh

set -euo pipefail

# Resolve project root (two levels up from tools/ssh/).
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ACCESS="${ROOT}/config/animon.yaml"
IDENTITY=""
DRY_RUN=0
NODE_FILTER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --identity) IDENTITY="${2:?--identity needs a value}"; shift 2 ;;
        --access)   ACCESS="${2:?--access needs a value}"; shift 2 ;;
        --dry-run)  DRY_RUN=1; shift ;;
        -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)         echo "error: unknown option: $1" >&2; exit 1 ;;
        *)          NODE_FILTER="$1"; shift ;;
    esac
done

command -v ssh-copy-id >/dev/null || { echo "error: ssh-copy-id not found — install OpenSSH client" >&2; exit 1; }
command -v python3 >/dev/null     || { echo "error: python3 not found (needed to parse animon.yaml)" >&2; exit 1; }
[[ -f "$ACCESS" ]] || { echo "error: access file not found: $ACCESS" >&2; echo "       Copy config/animon.example.yaml to config/animon.yaml first." >&2; exit 1; }

# Default identity: the dedicated fleet key if it exists.
if [[ -z "$IDENTITY" && -f "${HOME}/.ssh/animontics_ed25519.pub" ]]; then
    IDENTITY="${HOME}/.ssh/animontics_ed25519.pub"
fi
[[ -n "$IDENTITY" ]] || { echo "error: no public key found — run ./tools/ssh/gen_keys.sh or pass --identity" >&2; exit 1; }
[[ -f "$IDENTITY" ]] || { echo "error: identity file not found: $IDENTITY" >&2; exit 1; }

# Enumerate "user<TAB>host" lines from animon.yaml. Address preference:
# ip > wifi_ip > usb gadget usb_ip. Nodes with no reachable address are skipped.
mapfile -t TARGETS < <(python3 - "$ACCESS" "$NODE_FILTER" <<'PY'
import sys, yaml
path, node_filter = sys.argv[1], sys.argv[2]
with open(path) as f:
    cfg = yaml.safe_load(f) or {}
default_user = (cfg.get("defaults") or {}).get("ssh_user", "pi")
for node_id, node in (cfg.get("nodes") or {}).items():
    node = node or {}
    if node_filter and node_id != node_filter:
        continue
    user = node.get("ssh_user", default_user)
    conn = node.get("connection") or {}
    host = node.get("ip") or node.get("wifi_ip") or conn.get("usb_ip")
    if not host:
        sys.stderr.write(f"  skip {node_id}: no reachable address in animon.yaml\n")
        continue
    print(f"{user}\t{host}\t{node_id}")
PY
)

if [[ "${#TARGETS[@]}" -eq 0 ]]; then
    if [[ -n "$NODE_FILTER" ]]; then
        echo "error: node '$NODE_FILTER' not found (or has no address) in $ACCESS" >&2
    else
        echo "error: no nodes with reachable addresses in $ACCESS" >&2
    fi
    exit 1
fi

echo "Distributing public key: $IDENTITY"
echo "Access file:             $ACCESS"
echo ""

FAILED=0
for entry in "${TARGETS[@]}"; do
    IFS=$'\t' read -r user host node_id <<<"$entry"
    target="${user}@${host}"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [dry-run] ssh-copy-id -i $IDENTITY $target   ($node_id)"
        continue
    fi
    echo "── $node_id → $target ──────────────────"
    if ssh-copy-id -i "$IDENTITY" -o StrictHostKeyChecking=accept-new "$target"; then
        echo "  ok"
    else
        echo "  FAILED for $node_id ($target)" >&2
        FAILED=$((FAILED + 1))
    fi
    echo ""
done

if [[ "$FAILED" -gt 0 ]]; then
    echo "Done with $FAILED failure(s)." >&2
    exit 1
fi

echo "Done. Verify with: python -m tools.fleet.animon status"
