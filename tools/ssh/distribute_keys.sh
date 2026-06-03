#!/usr/bin/env bash
# distribute_keys.sh — Push your fleet public key to the boards (run on dev machine).
#
# Reads node access details from config/animon.yaml and runs ssh-copy-id against
# each one, so afterwards the animon CLI can connect with key auth (BatchMode).
# ssh-copy-id will prompt for each board's password ONCE — that initial password
# is never stored and never passed on the command line.
#
# Optional hardening: after the key is installed AND verified to work, --harden
# disables SSH password authentication on the board (drops a config file in
# /etc/ssh/sshd_config.d/). --unharden reverses it. Hardening is skipped for any
# board where key auth is not yet working, so you cannot lock yourself out.
#
# Usage:
#   ./tools/ssh/distribute_keys.sh                          # all nodes in animon.yaml
#   ./tools/ssh/distribute_keys.sh my_sbc_node              # one node
#   ./tools/ssh/distribute_keys.sh --identity ~/.ssh/animontics_ed25519.pub
#   ./tools/ssh/distribute_keys.sh --access path/to/animon.yaml
#   ./tools/ssh/distribute_keys.sh --harden                 # copy key, then disable password auth
#   ./tools/ssh/distribute_keys.sh --unharden               # re-enable password auth (no key copy)
#   ./tools/ssh/distribute_keys.sh --dry-run                # print actions, change nothing
#
# Prerequisite: generate a key first with ./tools/ssh/gen_keys.sh

set -euo pipefail

# Resolve project root (two levels up from tools/ssh/).
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ACCESS="${ROOT}/config/animon.yaml"
IDENTITY=""
DRY_RUN=0
NODE_FILTER=""
HARDEN=0
UNHARDEN=0

# Drop-in file we own on each board. Removing it restores the sshd default.
HARDEN_CONF="/etc/ssh/sshd_config.d/10-animontics-harden.conf"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --identity) IDENTITY="${2:?--identity needs a value}"; shift 2 ;;
        --access)   ACCESS="${2:?--access needs a value}"; shift 2 ;;
        --harden)   HARDEN=1; shift ;;
        --unharden) UNHARDEN=1; shift ;;
        --dry-run)  DRY_RUN=1; shift ;;
        -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)         echo "error: unknown option: $1" >&2; exit 1 ;;
        *)          NODE_FILTER="$1"; shift ;;
    esac
done

if [[ "$HARDEN" -eq 1 && "$UNHARDEN" -eq 1 ]]; then
    echo "error: --harden and --unharden are mutually exclusive" >&2
    exit 1
fi

# --unharden only re-enables password auth; it does not push a key.
COPY=1
[[ "$UNHARDEN" -eq 1 ]] && COPY=0

# Pick a working Python 3 (python3 on Linux/macOS, often just python on Windows).
# Running -c also rejects the Windows Store "python" stub, which exits non-zero.
PYTHON=""
for _py in python3 python; do
    if command -v "$_py" >/dev/null 2>&1 && "$_py" -c 'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
        PYTHON="$_py"; break
    fi
done
[[ -n "$PYTHON" ]] || { echo "error: no Python 3 found (tried python3, python) — needed to parse animon.yaml" >&2; exit 1; }
[[ -f "$ACCESS" ]] || { echo "error: access file not found: $ACCESS" >&2; echo "       Copy config/animon.example.yaml to config/animon.yaml first." >&2; exit 1; }

# Identity is needed to copy a key and to verify key auth before hardening.
PRIVKEY=""
if [[ "$COPY" -eq 1 || "$HARDEN" -eq 1 ]]; then
    command -v ssh-copy-id >/dev/null || { echo "error: ssh-copy-id not found — install OpenSSH client" >&2; exit 1; }
    if [[ -z "$IDENTITY" && -f "${HOME}/.ssh/animontics_ed25519.pub" ]]; then
        IDENTITY="${HOME}/.ssh/animontics_ed25519.pub"
    fi
    [[ -n "$IDENTITY" ]] || { echo "error: no public key found — run ./tools/ssh/gen_keys.sh or pass --identity" >&2; exit 1; }
    [[ -f "$IDENTITY" ]] || { echo "error: identity file not found: $IDENTITY" >&2; exit 1; }
    PRIVKEY="${IDENTITY%.pub}"
fi

# Enumerate "user<TAB>host<TAB>node_id" lines from animon.yaml. Address
# preference: ip > wifi_ip > usb gadget usb_ip. Unreachable nodes are skipped.
mapfile -t TARGETS < <("$PYTHON" - "$ACCESS" "$NODE_FILTER" <<'PY'
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

# Remote command strings. sshd -t validates the config before we restart, so a
# broken drop-in never takes down the SSH daemon. ssh vs sshd unit name varies.
read -r -d '' HARDEN_REMOTE <<EOF || true
set -e
printf '%s\n' '# Managed by animontics (tools/ssh/distribute_keys.sh --harden)' 'PasswordAuthentication no' 'KbdInteractiveAuthentication no' | sudo tee '$HARDEN_CONF' >/dev/null
sudo sshd -t
sudo systemctl restart ssh 2>/dev/null || sudo systemctl restart sshd
EOF

read -r -d '' UNHARDEN_REMOTE <<EOF || true
set -e
sudo rm -f '$HARDEN_CONF'
sudo sshd -t
sudo systemctl restart ssh 2>/dev/null || sudo systemctl restart sshd
EOF

harden_node() {
    local target="$1" node_id="$2"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [dry-run] verify key auth, then disable password auth on $target"
        return 0
    fi
    # Never disable password auth unless key auth already works on this board.
    local -a idopt=()
    [[ -n "$PRIVKEY" && -f "$PRIVKEY" ]] && idopt=(-i "$PRIVKEY")
    if ! ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
        "${idopt[@]}" "$target" true 2>/dev/null; then
        echo "  REFUSING to harden $node_id: key auth not working yet (would lock you out)" >&2
        return 1
    fi
    # -t so sudo can prompt if the board does not have passwordless sudo.
    if ssh -t -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new \
        "$target" "$HARDEN_REMOTE"; then
        echo "  hardened — password auth disabled"
    else
        echo "  FAILED to harden $node_id" >&2
        return 1
    fi
}

unharden_node() {
    local target="$1" node_id="$2"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [dry-run] re-enable password auth on $target"
        return 0
    fi
    if ssh -t -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new \
        "$target" "$UNHARDEN_REMOTE"; then
        echo "  unhardened — password auth re-enabled"
    else
        echo "  FAILED to unharden $node_id" >&2
        return 1
    fi
}

echo "Access file: $ACCESS"
[[ "$COPY" -eq 1 ]]     && echo "Distributing public key: $IDENTITY"
[[ "$HARDEN" -eq 1 ]]   && echo "Hardening: password auth will be disabled after key verification"
[[ "$UNHARDEN" -eq 1 ]] && echo "Unhardening: password auth will be re-enabled"
echo ""

FAILED=0
for entry in "${TARGETS[@]}"; do
    IFS=$'\t' read -r user host node_id <<<"$entry"
    target="${user}@${host}"
    echo "── $node_id → $target ──────────────────"

    if [[ "$COPY" -eq 1 ]]; then
        if [[ "$DRY_RUN" -eq 1 ]]; then
            echo "  [dry-run] ssh-copy-id -i $IDENTITY $target"
        elif ssh-copy-id -i "$IDENTITY" -o StrictHostKeyChecking=accept-new "$target"; then
            echo "  key installed"
        else
            echo "  FAILED to copy key for $node_id ($target)" >&2
            FAILED=$((FAILED + 1))
            echo ""
            continue
        fi
    fi

    if [[ "$HARDEN" -eq 1 ]]; then
        harden_node "$target" "$node_id" || FAILED=$((FAILED + 1))
    elif [[ "$UNHARDEN" -eq 1 ]]; then
        unharden_node "$target" "$node_id" || FAILED=$((FAILED + 1))
    fi
    echo ""
done

if [[ "$FAILED" -gt 0 ]]; then
    echo "Done with $FAILED failure(s)." >&2
    exit 1
fi

echo "Done. Verify with: python -m tools.fleet.animon status"
