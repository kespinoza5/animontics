# tools/ssh

Key-based SSH access provisioning for the fleet. Run these **on your dev
machine** — they set up the key auth the `animon` CLI relies on
(`tools/fleet/ssh.py` enforces `BatchMode=yes`, so password auth never works).

## Why key auth only

The fleet CLI connects non-interactively. It will not prompt for a password and
never passes credentials on the command line. Every board must trust your fleet
public key before `animon deploy` / `status` / `diff` can reach it.

## Quick start — `fleet_access.sh`

One wrapper stitches the individual scripts together for the common workflows.
Most of the time this is the only command you need:

```bash
./tools/ssh/fleet_access.sh setup            # gen key (if needed) + distribute + ssh-config
./tools/ssh/fleet_access.sh setup --harden   # ...and disable board password auth
./tools/ssh/fleet_access.sh refresh          # after editing animon.yaml: re-distribute + ssh-config
./tools/ssh/fleet_access.sh rotate --new ~/.ssh/animontics_new   # new key, distribute, repoint, revoke old
```

All three accept `--access`, `--prefix`, `--dry-run`, and a trailing node id to
scope to one board. After `setup`, `scp file <node-id>:/path` works with no `-i`
and no `ssh-add`. The individual scripts below are still available if you want to
run a single step.

## Tools

### `gen_keys.sh`

Generate a dedicated Ed25519 key pair for fleet access (separate from your
personal key, so it's easy to rotate). No passphrase by default so the CLI runs
unattended; `--passphrase` if you'd rather use one with `ssh-agent`.

```bash
./gen_keys.sh                       # ~/.ssh/animontics_ed25519[.pub]
./gen_keys.sh --path ~/.ssh/mykey   # custom location
./gen_keys.sh --passphrase          # prompt for a passphrase
```

It refuses to overwrite an existing key. The private key is yours alone — never
commit it.

### `distribute_keys.sh`

Push the public key to the boards listed in `config/animon.yaml` using
`ssh-copy-id`. Resolves each node's SSH user (per-node `ssh_user`, else
`defaults.ssh_user`) and address (preferring `ip`, then `wifi_ip`, then the USB
gadget `usb_ip`). `ssh-copy-id` prompts for each board's password **once** to
install the key — that password is never stored or echoed.

```bash
./distribute_keys.sh                       # every node in animon.yaml
./distribute_keys.sh my_sbc_node           # just one node
./distribute_keys.sh --identity ~/.ssh/animontics_ed25519.pub
./distribute_keys.sh --access path/to/animon.yaml
./distribute_keys.sh --dry-run             # print targets, copy nothing
```

If no `--identity` is given it defaults to `~/.ssh/animontics_ed25519.pub` when
that exists. Nodes with no reachable address in `animon.yaml` are skipped with a
warning. Exit code is non-zero if any copy fails.

#### Optional hardening

Once key auth works, you can lock password auth off entirely:

```bash
./distribute_keys.sh --harden      # copy key, verify it works, then disable password auth
./distribute_keys.sh --unharden    # re-enable password auth (no key copy)
```

`--harden` drops `/etc/ssh/sshd_config.d/10-animontics-harden.conf`
(`PasswordAuthentication no`) on each board, validates with `sshd -t`, and
restarts the SSH service. It **verifies key auth works first** and refuses to
harden any board where it doesn't, so you can't lock yourself out. `--unharden`
removes that file and restarts the service. Both need `sudo` on the board (the
script allocates a TTY so `sudo` can prompt if passwordless sudo isn't set up)
and rely on the board's sshd honouring `sshd_config.d/` includes (standard on
Raspberry Pi OS Bullseye and later).

### `revoke_keys.sh`

Remove a fleet public key from every board's `authorized_keys` — for revoking a
lost/old key or completing a key rotation. It matches on the key's base64 body
(so a changed comment doesn't matter) and **refuses to remove the last remaining
key** from a board unless `--force` is given.

```bash
./revoke_keys.sh --identity ~/.ssh/old_key.pub          # all nodes
./revoke_keys.sh --identity ~/.ssh/old_key.pub my_node  # one node
./revoke_keys.sh --identity ... --dry-run               # report only, change nothing
./revoke_keys.sh --identity ... --force                 # allow emptying authorized_keys
```

It connects with whatever key auth currently works, so run it **after** the
replacement key is in place.

### `setup_ssh_config.sh`

Writes a managed block into `~/.ssh/config` with one `Host` alias per node from
`animon.yaml`, each pinned to the fleet key (`IdentityFile` + `IdentitiesOnly`).
After running it, plain `scp`/`ssh`/`rsync` to a node alias work with **no `-i`
flag and no `ssh-add`** — the config selects the key for you:

```bash
./setup_ssh_config.sh                 # alias = <node-id>
./setup_ssh_config.sh --prefix animon-  # alias = animon-<node-id> (avoids name clashes)
./setup_ssh_config.sh --dry-run       # print the block, write nothing

scp firmware.uf2 my_sbc_node:/tmp/    # just works
```

Re-running refreshes the block in place (between markers); your other
`~/.ssh/config` entries are untouched and the previous file is saved to
`~/.ssh/config.bak`.

## Typical first-time flow

```bash
./tools/ssh/gen_keys.sh
./tools/ssh/distribute_keys.sh             # ssh-add not needed if you run setup_ssh_config.sh
./tools/ssh/setup_ssh_config.sh            # makes ssh/scp <node-id> just work
python -m tools.fleet.animon status        # confirm key auth works
./tools/ssh/distribute_keys.sh --harden    # (optional) lock off password auth
```

## Direction of trust (one-way)

These tools authorize **dev machine → node** only: your dev machine's public key
is installed on the boards. The reverse (a node initiating SSH/scp back to the
dev machine) is **not** set up and would need an SSH server on the dev machine
plus each node's public key installed there. See `TODO.md` (Tools) if that
becomes necessary.

## Rotating the fleet key

```bash
./tools/ssh/gen_keys.sh --path ~/.ssh/animontics_new
./tools/ssh/distribute_keys.sh --identity ~/.ssh/animontics_new.pub
ssh-add ~/.ssh/animontics_new              # connect with the new key from now on
./tools/ssh/revoke_keys.sh --identity ~/.ssh/animontics_ed25519.pub   # remove the old one
```
