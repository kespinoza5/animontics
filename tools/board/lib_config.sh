#!/usr/bin/env bash
# lib_config.sh — shared helpers for the board interface setup scripts.
#
# Sourced by setup_i2c.sh / setup_uart.sh / setup_spi.sh / setup_i2s.sh.
# Not meant to be run directly. All functions are idempotent: re-running a
# setup script never duplicates a line or undoes a previous edit.
#
# Target platform: Raspberry Pi OS (Bookworm and earlier). The firmware config
# file moved from /boot/config.txt to /boot/firmware/config.txt in Bookworm;
# find_config_txt() handles both. Orange Pi / Armbian boards use a different
# mechanism (armbianEnv.txt + overlays) — these scripts do NOT cover them; use
# `armbian-config` there. See tools/board/README.md.

# Guard against being executed directly.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "lib_config.sh is a helper library — source it, don't run it." >&2
    exit 1
fi

# Colours only when stdout is a terminal.
if [[ -t 1 ]]; then
    C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_INFO=$'\033[36m'; C_RST=$'\033[0m'
else
    C_OK=''; C_WARN=''; C_INFO=''; C_RST=''
fi

info() { echo "  ${C_INFO}$*${C_RST}"; }
ok()   { echo "  ${C_OK}$*${C_RST}"; }
warn() { echo "  ${C_WARN}$*${C_RST}" >&2; }
die()  { echo "${C_WARN}error:${C_RST} $*" >&2; exit 1; }

# require_root — re-exec under sudo if not already root.
require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        die "must run as root — try: sudo $0 $*"
    fi
}

# find_config_txt — echo the path to the active firmware config.txt.
# Prefers the Bookworm location, falls back to the legacy one.
find_config_txt() {
    if [[ -f /boot/firmware/config.txt ]]; then
        echo /boot/firmware/config.txt
    elif [[ -f /boot/config.txt ]]; then
        echo /boot/config.txt
    else
        die "no config.txt found in /boot/firmware or /boot — is this a Raspberry Pi?"
    fi
}

# find_cmdline_txt — echo the path to the active kernel cmdline file.
find_cmdline_txt() {
    if [[ -f /boot/firmware/cmdline.txt ]]; then
        echo /boot/firmware/cmdline.txt
    elif [[ -f /boot/cmdline.txt ]]; then
        echo /boot/cmdline.txt
    else
        die "no cmdline.txt found in /boot/firmware or /boot"
    fi
}

# backup_once FILE — make a one-time .anim.bak backup the first time we touch
# a file, so the original can always be restored.
backup_once() {
    local file="$1"
    if [[ ! -f "${file}.anim.bak" ]]; then
        cp "$file" "${file}.anim.bak"
        info "backed up $file -> ${file}.anim.bak"
    fi
}

# ensure_line FILE LINE [MATCH]
#   Guarantee FILE contains LINE exactly once.
#   - If MATCH (a regex) is given and an existing line matches it, that line is
#     replaced in place (handles e.g. changing a baud rate value).
#   - Otherwise, if LINE is already present verbatim, nothing happens.
#   - Otherwise LINE is appended.
ensure_line() {
    local file="$1" line="$2" match="${3:-}"
    backup_once "$file"

    if [[ -n "$match" ]] && grep -Eq "$match" "$file"; then
        # Replace the matching line in place (escape & and / for sed RHS).
        local esc=${line//\\/\\\\}; esc=${esc//&/\\&}; esc=${esc//\//\\/}
        sed -i -E "s/${match}/${esc}/" "$file"
        ok "set: $line"
    elif grep -Fxq "$line" "$file"; then
        info "already set: $line"
    else
        printf '%s\n' "$line" >> "$file"
        ok "added: $line"
    fi
}

# comment_out FILE REGEX — comment out (prefix '#') any uncommented line
# matching REGEX. Idempotent: already-commented lines are left alone.
comment_out() {
    local file="$1" regex="$2"
    backup_once "$file"
    if grep -Eq "^[[:space:]]*${regex}" "$file"; then
        sed -i -E "s|^([[:space:]]*)(${regex})|\1# \2|" "$file"
        ok "commented out lines matching: $regex"
    else
        info "no active lines matching: $regex"
    fi
}

# reboot_notice — uniform closing message.
reboot_notice() {
    echo ""
    echo "  ${C_WARN}A reboot is required for changes to take effect:${C_RST}"
    echo "      sudo reboot"
    echo ""
    echo "  Then verify with: tools/board/verify_comms.sh"
}
