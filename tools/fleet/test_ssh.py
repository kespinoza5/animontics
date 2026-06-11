"""Unit tests for the SSH transport wrapper — command construction and quoting.

No network: subprocess.run is monkeypatched to capture the argv that *would*
run, so these verify key-only auth flags and that remote paths/content are
shell-quoted (a path can never inject into the remote shell).
"""
from __future__ import annotations

import shlex
import subprocess
from types import SimpleNamespace

import pytest

from tools.fleet import ssh as fleet_ssh
from tools.fleet.ssh import (
    SSHError,
    read_remote_file,
    remove_remote_dir,
    run_remote,
    write_remote_file,
)


@pytest.fixture
def capture(monkeypatch):
    """Capture subprocess.run argv; respond with a configurable result."""
    calls: list[list[str]] = []
    result = SimpleNamespace(stdout="", stderr="", returncode=0)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    return SimpleNamespace(calls=calls, result=result)


def _remote_cmd(argv: list[str]) -> str:
    """The shell command sent to the remote host (last ssh argument)."""
    return argv[-1]


# ── run_remote ────────────────────────────────────────────────────────────────

def test_run_remote_enforces_batchmode_key_auth(capture):
    run_remote("h", "u", "true")
    argv = capture.calls[0]
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv          # never falls back to password auth
    assert "u@h" in argv


def test_run_remote_raises_on_nonzero_when_checked(capture):
    capture.result.returncode = 7
    capture.result.stderr = "boom"
    with pytest.raises(SSHError, match="exit 7"):
        run_remote("h", "u", "false")


def test_run_remote_no_raise_when_uncheck(capture):
    capture.result.returncode = 7
    _, _, rc = run_remote("h", "u", "false", check=False)
    assert rc == 7


def test_run_remote_dry_run_executes_nothing(capture):
    out = run_remote("h", "u", "rm -rf /", dry_run=True)
    assert capture.calls == []
    assert out == ("", "", 0)


def test_run_remote_timeout_becomes_ssherror(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 30)
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SSHError, match="timed out"):
        run_remote("h", "u", "sleep 99")


# ── path/content quoting ─────────────────────────────────────────────────────

HOSTILE_PATH = "/tmp/odd name/'$(reboot)'/config.yaml"


def test_read_remote_file_quotes_path(capture):
    capture.result.stdout = "data"
    read_remote_file("h", "u", HOSTILE_PATH)
    cmd = _remote_cmd(capture.calls[0])
    assert shlex.quote(HOSTILE_PATH) in cmd
    # The dangerous substring must not appear unquoted as its own shell word.
    assert "$(reboot)" in shlex.quote(HOSTILE_PATH)  # sanity: it's inside quotes


def test_write_remote_file_quotes_path_and_content(capture):
    content = "key: 'va$lue'\nline2: `tick`\n"
    write_remote_file("h", "u", HOSTILE_PATH, content)
    cmd = _remote_cmd(capture.calls[0])
    assert shlex.quote(HOSTILE_PATH) in cmd
    assert shlex.quote(content) in cmd
    # Round-trip sanity: the quoted form parses back to the original payload.
    assert shlex.split(shlex.quote(content)) == [content]


def test_write_remote_file_dry_run_writes_nothing(capture):
    write_remote_file("h", "u", "/tmp/x", "abc", dry_run=True)
    assert capture.calls == []


def test_remove_remote_dir_quotes_path(capture):
    remove_remote_dir("h", "u", HOSTILE_PATH)
    cmd = _remote_cmd(capture.calls[0])
    assert cmd == f"rm -rf {shlex.quote(HOSTILE_PATH)}"


def test_ssh_missing_binary_is_clear_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SSHError, match="ssh not found"):
        run_remote("h", "u", "true")
