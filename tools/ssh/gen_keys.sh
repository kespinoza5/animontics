#!/usr/bin/env bash
# gen_keys.sh — Generate an SSH key pair for fleet access (run on your dev machine).
#
# The animon fleet CLI uses SSH key auth only (BatchMode=yes — no passwords).
# This creates a dedicated Ed25519 key pair for reaching the boards, so fleet
# access is separate from your personal key and easy to rotate.
#
# Usage:
#   ./tools/ssh/gen_keys.sh                          # ~/.ssh/animontics_ed25519
#   ./tools/ssh/gen_keys.sh --path ~/.ssh/mykey      # custom path
#   ./tools/ssh/gen_keys.sh --passphrase             # prompt for a passphrase
#
# By default the key has NO passphrase so the CLI can run unattended. Use
# --passphrase if you prefer one and are running ssh-agent (ssh-add) to cache it.
#
# Next step: push the public key to the boards with
#   ./tools/ssh/distribute_keys.sh

set -euo pipefail

KEY_PATH="${HOME}/.ssh/animontics_ed25519"
USE_PASSPHRASE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --path)       KEY_PATH="${2:?--path needs a value}"; shift 2 ;;
        --passphrase) USE_PASSPHRASE=1; shift ;;
        -h|--help)    grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)            echo "error: unknown argument: $1" >&2; exit 1 ;;
    esac
done

command -v ssh-keygen >/dev/null || { echo "error: ssh-keygen not found — install OpenSSH" >&2; exit 1; }

if [[ -e "$KEY_PATH" ]]; then
    echo "error: $KEY_PATH already exists — refusing to overwrite." >&2
    echo "       Pick another --path or remove the old key first." >&2
    exit 1
fi

mkdir -p "$(dirname "$KEY_PATH")"
chmod 700 "$(dirname "$KEY_PATH")"

COMMENT="animontics-fleet-$(whoami)@$(hostname)"

if [[ "$USE_PASSPHRASE" -eq 1 ]]; then
    ssh-keygen -t ed25519 -f "$KEY_PATH" -C "$COMMENT"
else
    ssh-keygen -t ed25519 -f "$KEY_PATH" -C "$COMMENT" -N ""
fi

echo ""
echo "Key pair created:"
echo "  private: $KEY_PATH        (keep secret — never commit)"
echo "  public:  ${KEY_PATH}.pub"
echo ""
echo "Next steps:"
echo "  1. Load it into your agent:   ssh-add \"$KEY_PATH\""
echo "  2. Push it to the fleet:      ./tools/ssh/distribute_keys.sh --identity \"${KEY_PATH}.pub\""
