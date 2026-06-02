"""SSH and rsync transport abstraction.

Wraps the system ssh/rsync CLI tools — no additional Python dependencies.
All operations accept a dry_run flag; when True they print what would run
without executing anything.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class SSHError(Exception):
    """Raised when a remote command exits with a non-zero status."""


def _ssh_target(user: str, host: str) -> str:
    return f"{user}@{host}"


def run_remote(
    host: str,
    user: str,
    cmd: str,
    *,
    dry_run: bool = False,
    check: bool = True,
    timeout: int = 30,
) -> tuple[str, str, int]:
    """Run a shell command on a remote host via SSH.

    Args:
        host:    Target hostname or IP address.
        user:    SSH user.
        cmd:     Shell command to execute remotely.
        dry_run: If True, print the command but do not execute it.
        check:   If True, raise SSHError on non-zero exit code.
        timeout: Command timeout in seconds.

    Returns:
        Tuple of (stdout, stderr, returncode).

    Raises:
        SSHError: if check=True and the remote command fails.
    """
    full_cmd = [
        "ssh",
        "-o", "BatchMode=yes",            # fail fast if no key auth
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
        _ssh_target(user, host),
        cmd,
    ]
    if dry_run:
        print(f"[dry-run] ssh {_ssh_target(user, host)} {cmd!r}")
        return ("", "", 0)

    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise SSHError(f"SSH command timed out after {timeout}s: {cmd!r}")
    except FileNotFoundError:
        raise SSHError("ssh not found — install OpenSSH client")

    if check and result.returncode != 0:
        raise SSHError(
            f"Remote command failed (exit {result.returncode}):\n"
            f"  cmd:    {cmd!r}\n"
            f"  stderr: {result.stderr.strip()}"
        )
    return (result.stdout, result.stderr, result.returncode)


def read_remote_file(host: str, user: str, path: str) -> str | None:
    """Read a file from a remote host. Returns None if the file does not exist."""
    stdout, _, rc = run_remote(host, user, f"cat {path} 2>/dev/null", check=False)
    return stdout if rc == 0 and stdout else None


def write_remote_file(
    host: str,
    user: str,
    path: str,
    content: str,
    *,
    dry_run: bool = False,
) -> None:
    """Write content to a file on a remote host using a heredoc."""
    if dry_run:
        print(f"[dry-run] write {len(content)} bytes → {_ssh_target(user, host)}:{path}")
        return

    # Use printf to avoid shell escaping issues with heredocs and special chars
    escaped = content.replace("\\", "\\\\").replace("'", "'\\''")
    run_remote(
        host, user,
        f"mkdir -p $(dirname {path}) && printf '%s' '{escaped}' > {path}",
        dry_run=False,
    )


def rsync_to(
    local: Path,
    host: str,
    user: str,
    remote: str,
    *,
    delete: bool = False,
    dry_run: bool = False,
) -> None:
    """Rsync a local file or directory to a remote path.

    Args:
        local:   Local path (file or directory).
        host:    Target hostname or IP.
        user:    SSH user.
        remote:  Remote destination path.
        delete:  If True, remove remote files not present locally.
        dry_run: If True, pass --dry-run to rsync (shows what would change).
    """
    cmd = [
        "rsync", "-az", "--progress",
        "-e", "ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new",
    ]
    if delete:
        cmd.append("--delete")
    if dry_run:
        cmd.append("--dry-run")

    src = str(local) + ("/" if local.is_dir() else "")
    dst = f"{_ssh_target(user, host)}:{remote}"
    cmd += [src, dst]

    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
    except FileNotFoundError:
        raise SSHError("rsync not found — install rsync")

    if result.returncode != 0:
        raise SSHError(f"rsync failed (exit {result.returncode})")


def remove_remote_dir(
    host: str,
    user: str,
    path: str,
    *,
    dry_run: bool = False,
) -> None:
    """Remove a directory on a remote host."""
    run_remote(host, user, f"rm -rf {path}", dry_run=dry_run)
