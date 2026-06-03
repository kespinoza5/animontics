#!/usr/bin/env bash
# setup_ssh_config.sh — Make `ssh <node>` / `scp file <node>:/path` just work.
#
# Writes a managed fleet block into ~/.ssh/config with one Host entry per node
# from config/animon.yaml, each pinned to the dedicated fleet key. After this you
# can do `scp foo.txt my_node:/tmp/` with no -i flag and no ssh-add — IdentityFile
# + IdentitiesOnly in the config handle key selection for you.
#
# Re-running refreshes the block in place (delimited by markers); any other
# entries in ~/.ssh/config are left untouched. The previous file is backed up to
# ~/.ssh/config.bak.
#
# Usage:
#   ./tools/ssh/setup_ssh_config.sh
#   ./tools/ssh/setup_ssh_config.sh --identity ~/.ssh/animontics_ed25519
#   ./tools/ssh/setup_ssh_config.sh --prefix animon-     # aliases like animon-<node>
#   ./tools/ssh/setup_ssh_config.sh --access path/to/animon.yaml
#   ./tools/ssh/setup_ssh_config.sh --dry-run            # print the block, write nothing
#
# Prereq: ./tools/ssh/gen_keys.sh and ./tools/ssh/distribute_keys.sh

set -euo pipefail

# Resolve project root (two levels up from tools/ssh/).
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ACCESS="${ROOT}/config/animon.yaml"
IDENTITY=""
PREFIX=""
DRY_RUN=0
SSH_CONFIG="${HOME}/.ssh/config"

BEGIN_MARK="# >>> animontics fleet (managed by tools/ssh/setup_ssh_config.sh) >>>"
END_MARK="# <<< animontics fleet <<<"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --identity) IDENTITY="${2:?--identity needs a value}"; shift 2 ;;
        --access)   ACCESS="${2:?--access needs a value}"; shift 2 ;;
        --prefix)   PREFIX="${2:?--prefix needs a value}"; shift 2 ;;
        --dry-run)  DRY_RUN=1; shift ;;
        -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)         echo "error: unknown option: $1" >&2; exit 1 ;;
        *)          echo "error: unexpected argument: $1" >&2; exit 1 ;;
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
[[ -f "$ACCESS" ]] || { echo "error: access file not found: $ACCESS" >&2; echo "       Copy config/animon.example.yaml to config/animon.yaml first." >&2; exit 1; }

# IdentityFile written into the config. Default keeps the ~ form (both git-bash
# and native OpenSSH understand it); a custom path is used verbatim (sans .pub).
IDENTITY="${IDENTITY%.pub}"
[[ -n "$IDENTITY" ]] || IDENTITY="~/.ssh/animontics_ed25519"
IDENTITY_CHECK="${IDENTITY/#\~/$HOME}"
[[ -f "$IDENTITY_CHECK" ]] || { echo "error: private key not found: $IDENTITY_CHECK" >&2; echo "       Run ./tools/ssh/gen_keys.sh or pass --identity." >&2; exit 1; }

# Build one Host stanza per node. IdentitiesOnly avoids 'too many auth failures'
# by offering only the fleet key; accept-new matches the rest of the fleet tools.
BODY="$("$PYTHON" - "$ACCESS" "$IDENTITY" "$PREFIX" <<'PY'
import sys, yaml
path, identity, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    cfg = yaml.safe_load(f) or {}
default_user = (cfg.get("defaults") or {}).get("ssh_user", "pi")
stanzas = []
for node_id, node in (cfg.get("nodes") or {}).items():
    node = node or {}
    user = node.get("ssh_user", default_user)
    conn = node.get("connection") or {}
    host = node.get("ip") or node.get("wifi_ip") or conn.get("usb_ip")
    if not host:
        sys.stderr.write(f"  skip {node_id}: no reachable address in animon.yaml\n")
        continue
    stanzas.append(
        f"Host {prefix}{node_id}\n"
        f"    HostName {host}\n"
        f"    User {user}\n"
        f"    IdentityFile {identity}\n"
        f"    IdentitiesOnly yes\n"
        f"    StrictHostKeyChecking accept-new"
    )
print("\n\n".join(stanzas))
PY
)"

[[ -n "$BODY" ]] || { echo "error: no nodes with reachable addresses in $ACCESS" >&2; exit 1; }

HEADER="# Generated $(date '+%Y-%m-%d %H:%M:%S') from ${ACCESS} — edits between the markers are overwritten."
BLOCK="${BEGIN_MARK}
${HEADER}
${BODY}
${END_MARK}"

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] would write this block to $SSH_CONFIG:"
    echo ""
    echo "$BLOCK"
    exit 0
fi

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

TMP="${SSH_CONFIG}.tmp.$$"
if [[ -f "$SSH_CONFIG" ]]; then
    cp "$SSH_CONFIG" "${SSH_CONFIG}.bak"
    # Drop any existing managed block, keep everything else.
    awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
        $0==b {skip=1}
        skip && $0==e {skip=0; next}
        !skip {print}
    ' "$SSH_CONFIG" > "$TMP"
    # Separate the block from preceding content with one blank line.
    [[ -s "$TMP" ]] && printf '\n' >> "$TMP"
else
    : > "$TMP"
fi

printf '%s\n' "$BLOCK" >> "$TMP"
mv "$TMP" "$SSH_CONFIG"
chmod 600 "$SSH_CONFIG"

NODE_COUNT="$(printf '%s\n' "$BODY" | grep -c '^Host ')"
echo "Wrote $NODE_COUNT fleet host alias(es) to $SSH_CONFIG"
[[ -f "${SSH_CONFIG}.bak" ]] && echo "Previous config backed up to ${SSH_CONFIG}.bak"
echo ""
echo "Now: scp file ${PREFIX}<node-id>:/path   (no -i, no ssh-add needed)"
