#!/usr/bin/env bash
# revoke_keys.sh — Remove a fleet public key from the boards' authorized_keys.
#
# Use this to revoke a lost/old key, or as the final step of key rotation:
#   1. ./tools/ssh/gen_keys.sh --path ~/.ssh/animontics_new
#   2. ./tools/ssh/distribute_keys.sh --identity ~/.ssh/animontics_new.pub
#   3. ssh-add ~/.ssh/animontics_new        # connect with the NEW key from now on
#   4. ./tools/ssh/revoke_keys.sh --identity ~/.ssh/animontics_ed25519.pub
#
# It connects with whatever key auth currently works (BatchMode), so run it
# AFTER the replacement key is in place. It refuses to remove the last remaining
# key from a board unless --force is given, so you cannot lock yourself out.
#
# Usage:
#   ./tools/ssh/revoke_keys.sh --identity ~/.ssh/old_key.pub          # all nodes
#   ./tools/ssh/revoke_keys.sh --identity ~/.ssh/old_key.pub my_node  # one node
#   ./tools/ssh/revoke_keys.sh --identity ... --access path/to/animon.yaml
#   ./tools/ssh/revoke_keys.sh --identity ... --dry-run               # report only
#   ./tools/ssh/revoke_keys.sh --identity ... --force                 # allow emptying authorized_keys

set -euo pipefail

# Resolve project root (two levels up from tools/ssh/).
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ACCESS="${ROOT}/config/animon.yaml"
IDENTITY=""
DRY_RUN=0
FORCE=0
NODE_FILTER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --identity) IDENTITY="${2:?--identity needs a value}"; shift 2 ;;
        --access)   ACCESS="${2:?--access needs a value}"; shift 2 ;;
        --force)    FORCE=1; shift ;;
        --dry-run)  DRY_RUN=1; shift ;;
        -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)         echo "error: unknown option: $1" >&2; exit 1 ;;
        *)          NODE_FILTER="$1"; shift ;;
    esac
done

# Pick a working Python 3 (python3 on Linux/macOS, often just python on Windows).
# Running -c also rejects the Windows Store "python" stub, which exits non-zero.
PYTHON=""
for _py in python3 python; do
    if command -v "$_py" >/dev/null 2>&1 && "$_py" -c 'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
        PYTHON="$_py"; break
    fi
done
[[ -n "$PYTHON" ]] || { echo "error: no Python 3 found (tried python3, python) — needed to parse animon.yaml" >&2; exit 1; }
[[ -n "$IDENTITY" ]] || { echo "error: --identity <pubkey> is required (the key to revoke)" >&2; exit 1; }
[[ -f "$IDENTITY" ]] || { echo "error: identity file not found: $IDENTITY" >&2; exit 1; }
[[ -f "$ACCESS" ]]   || { echo "error: access file not found: $ACCESS" >&2; echo "       Copy config/animon.example.yaml to config/animon.yaml first." >&2; exit 1; }

# The base64 key material (field 2) uniquely identifies the key regardless of
# the trailing comment, so match on that rather than the whole line.
KEYBODY="$(awk '{print $2}' "$IDENTITY")"
[[ -n "$KEYBODY" ]] || { echo "error: could not read a public key from $IDENTITY" >&2; exit 1; }

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

# Remote script: removes any authorized_keys line containing the key body.
# Args: $1=key body, $2=force (0/1), $3=dry-run (0/1).
read -r -d '' REMOTE <<'SCRIPT' || true
set -eu
key="$1"; force="$2"; dry="$3"
auth="$HOME/.ssh/authorized_keys"
[ -f "$auth" ] || { echo NOFILE; exit 0; }
grep -qF "$key" "$auth" || { echo ABSENT; exit 0; }
if [ "$dry" = "1" ]; then echo WOULD_REMOVE; exit 0; fi
remaining="$(grep -vF "$key" "$auth" || true)"
if [ -z "$remaining" ] && [ "$force" != "1" ]; then echo WOULD_EMPTY; exit 0; fi
if [ -z "$remaining" ]; then : > "$auth"; else printf '%s\n' "$remaining" > "$auth"; fi
chmod 600 "$auth"
echo REMOVED
SCRIPT

echo "Revoking key: $IDENTITY"
echo "Access file:  $ACCESS"
[[ "$DRY_RUN" -eq 1 ]] && echo "(dry-run — no changes will be made)"
echo ""

FAILED=0
for entry in "${TARGETS[@]}"; do
    IFS=$'\t' read -r user host node_id <<<"$entry"
    target="${user}@${host}"
    echo "── $node_id → $target ──────────────────"
    result="$(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
        "$target" bash -s "$KEYBODY" "$FORCE" "$DRY_RUN" <<<"$REMOTE" 2>/dev/null || echo SSHFAIL)"
    case "$result" in
        REMOVED)      echo "  removed" ;;
        WOULD_REMOVE) echo "  would remove (dry-run)" ;;
        ABSENT)       echo "  not present (nothing to do)" ;;
        NOFILE)       echo "  no authorized_keys file (nothing to do)" ;;
        WOULD_EMPTY)  echo "  REFUSING: this is the last key — re-run with --force to remove anyway" >&2; FAILED=$((FAILED + 1)) ;;
        SSHFAIL)      echo "  FAILED to connect to $node_id ($target)" >&2; FAILED=$((FAILED + 1)) ;;
        *)            echo "  unexpected result: $result" >&2; FAILED=$((FAILED + 1)) ;;
    esac
    echo ""
done

if [[ "$FAILED" -gt 0 ]]; then
    echo "Done with $FAILED failure(s)." >&2
    exit 1
fi

echo "Done. Verify with: python -m tools.fleet.animon status"
