#!/usr/bin/env bash
# fleet_access.sh — one entry point that stitches the tools/ssh/ scripts together
# for the common fleet-access workflows. Run on your dev machine.
#
# Commands:
#   setup    First-time onboarding: generate the fleet key if missing, push it to
#            every board, then write the ~/.ssh/config aliases so ssh/scp <node>
#            just work. Add --harden to disable board password auth afterwards.
#
#   refresh  After editing animon.yaml (new/changed nodes): re-push the key and
#            regenerate the ~/.ssh/config block. Does NOT generate a new key.
#
#   rotate   Replace the fleet key: generate a new key, push it, repoint the
#            ~/.ssh/config aliases at it, then revoke the old key from the boards.
#
# Usage:
#   ./tools/ssh/fleet_access.sh setup   [node] [--harden] [--identity ~/.ssh/key] [--access F] [--prefix P] [--dry-run]
#   ./tools/ssh/fleet_access.sh refresh [node] [--identity ~/.ssh/key] [--access F] [--prefix P] [--dry-run]
#   ./tools/ssh/fleet_access.sh rotate  --new ~/.ssh/animontics_new [--old ~/.ssh/animontics_ed25519.pub] [--access F] [--prefix P] [--dry-run]
#
# --identity takes the PRIVATE key path (the matching .pub is derived). Default
# is ~/.ssh/animontics_ed25519.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

GEN="${HERE}/gen_keys.sh"
DISTRIBUTE="${HERE}/distribute_keys.sh"
CONFIGURE="${HERE}/setup_ssh_config.sh"
REVOKE="${HERE}/revoke_keys.sh"

DEFAULT_KEY="${HOME}/.ssh/animontics_ed25519"

# ---- parse ----------------------------------------------------------------
[[ $# -ge 1 ]] || { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
CMD="$1"; shift

NODE=""
IDENTITY=""          # private key path (display form, may contain ~)
NEW_KEY=""
OLD_PUB=""
ACCESS=""
PREFIX=""
HARDEN=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --identity) IDENTITY="${2:?--identity needs a value}"; shift 2 ;;
        --new)      NEW_KEY="${2:?--new needs a value}"; shift 2 ;;
        --old)      OLD_PUB="${2:?--old needs a value}"; shift 2 ;;
        --access)   ACCESS="${2:?--access needs a value}"; shift 2 ;;
        --prefix)   PREFIX="${2:?--prefix needs a value}"; shift 2 ;;
        --harden)   HARDEN=1; shift ;;
        --dry-run)  DRY_RUN=1; shift ;;
        -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)         echo "error: unknown option: $1" >&2; exit 1 ;;
        *)          NODE="$1"; shift ;;
    esac
done

# Normalize a key path to its private form (strip a trailing .pub).
priv_of() { echo "${1%.pub}"; }
# Expand a leading ~ for filesystem checks.
expand() { echo "${1/#\~/$HOME}"; }

# Pass-through option arrays for the sub-tools.
ACCESS_OPT=();  [[ -n "$ACCESS" ]] && ACCESS_OPT=(--access "$ACCESS")
PREFIX_OPT=();  [[ -n "$PREFIX" ]] && PREFIX_OPT=(--prefix "$PREFIX")
DRY_OPT=();     [[ "$DRY_RUN" -eq 1 ]] && DRY_OPT=(--dry-run)

run() { echo "+ $*"; "$@"; }

# ---- commands -------------------------------------------------------------
case "$CMD" in
    setup)
        PRIV="$(priv_of "${IDENTITY:-$DEFAULT_KEY}")"
        PUB="${PRIV}.pub"
        if [[ ! -f "$(expand "$PRIV")" ]]; then
            echo "== Generating fleet key: $PRIV =="
            if [[ "$DRY_RUN" -eq 1 ]]; then
                echo "+ $GEN --path $PRIV   (skipped in dry-run)"
            else
                run "$GEN" --path "$PRIV"
            fi
        else
            echo "== Fleet key already exists: $PRIV =="
        fi

        echo "== Distributing key to boards =="
        DIST=("$DISTRIBUTE" --identity "$PUB" "${ACCESS_OPT[@]}" "${DRY_OPT[@]}")
        [[ "$HARDEN" -eq 1 ]] && DIST+=(--harden)
        [[ -n "$NODE" ]] && DIST+=("$NODE")
        run "${DIST[@]}"

        echo "== Writing ~/.ssh/config aliases =="
        run "$CONFIGURE" --identity "$PRIV" "${ACCESS_OPT[@]}" "${PREFIX_OPT[@]}" "${DRY_OPT[@]}"

        echo ""
        echo "Done. Verify with: python -m tools.fleet.animon status"
        ;;

    refresh)
        PRIV="$(priv_of "${IDENTITY:-$DEFAULT_KEY}")"
        PUB="${PRIV}.pub"
        [[ -f "$(expand "$PUB")" ]] || { echo "error: public key not found: $PUB — run 'setup' first or pass --identity" >&2; exit 1; }

        echo "== Re-distributing key to boards =="
        DIST=("$DISTRIBUTE" --identity "$PUB" "${ACCESS_OPT[@]}" "${DRY_OPT[@]}")
        [[ -n "$NODE" ]] && DIST+=("$NODE")
        run "${DIST[@]}"

        echo "== Refreshing ~/.ssh/config aliases =="
        run "$CONFIGURE" --identity "$PRIV" "${ACCESS_OPT[@]}" "${PREFIX_OPT[@]}" "${DRY_OPT[@]}"
        ;;

    rotate)
        [[ -n "$NEW_KEY" ]] || { echo "error: rotate requires --new <path-for-new-key>" >&2; exit 1; }
        NEW_PRIV="$(priv_of "$NEW_KEY")"
        NEW_PUB="${NEW_PRIV}.pub"
        OLD_PUB="${OLD_PUB:-${DEFAULT_KEY}.pub}"

        if [[ ! -f "$(expand "$NEW_PRIV")" ]]; then
            echo "== Generating new fleet key: $NEW_PRIV =="
            if [[ "$DRY_RUN" -eq 1 ]]; then
                echo "+ $GEN --path $NEW_PRIV   (skipped in dry-run)"
            else
                run "$GEN" --path "$NEW_PRIV"
            fi
        fi

        echo "== Distributing NEW key to boards =="
        run "$DISTRIBUTE" --identity "$NEW_PUB" "${ACCESS_OPT[@]}" "${DRY_OPT[@]}"

        echo "== Repointing ~/.ssh/config aliases at the new key =="
        run "$CONFIGURE" --identity "$NEW_PRIV" "${ACCESS_OPT[@]}" "${PREFIX_OPT[@]}" "${DRY_OPT[@]}"

        # revoke_keys connects with whatever key auth works; load the NEW key so
        # we don't depend on the old one still being installed.
        if [[ "$DRY_RUN" -eq 1 ]]; then
            echo "+ ssh-add $NEW_PRIV   (skipped in dry-run)"
        elif command -v ssh-add >/dev/null 2>&1; then
            run ssh-add "$(expand "$NEW_PRIV")" || echo "  (ssh-add failed — ensure the new key can reach the boards before revoking)"
        fi

        echo "== Revoking OLD key from boards =="
        run "$REVOKE" --identity "$OLD_PUB" "${ACCESS_OPT[@]}" "${DRY_OPT[@]}"

        echo ""
        echo "Rotation complete. The old key ($OLD_PUB) is no longer trusted by the fleet."
        ;;

    -h|--help|help)
        grep '^#' "$0" | sed 's/^# \{0,1\}//'
        ;;

    *)
        echo "error: unknown command '$CMD' (expected: setup | refresh | rotate)" >&2
        exit 1
        ;;
esac
