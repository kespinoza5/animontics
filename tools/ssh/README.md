# tools/ssh

Key-based SSH access provisioning for the fleet. Run these **on your dev
machine** — they set up the key auth the `animon` CLI relies on
(`tools/fleet/ssh.py` enforces `BatchMode=yes`, so password auth never works).

## Why key auth only

The fleet CLI connects non-interactively. It will not prompt for a password and
never passes credentials on the command line. Every board must trust your fleet
public key before `animon deploy` / `status` / `diff` can reach it.

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

## Typical first-time flow

```bash
./tools/ssh/gen_keys.sh
ssh-add ~/.ssh/animontics_ed25519
./tools/ssh/distribute_keys.sh
python -m tools.fleet.animon status        # confirm key auth works
```
