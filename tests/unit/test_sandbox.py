"""Tests for home_swe_home.sandbox."""

from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace

from anima import Context

from home_swe_home.sandbox import SandboxResult, SandboxService, run_in_sandbox


def _completed(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_sandbox_service_run(monkeypatch):
    """SandboxService.run delegates to run_in_sandbox via its params."""
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SandboxResult(stdout="ok\n", stderr="", exit_code=0, timed_out=False)

    monkeypatch.setattr("home_swe_home.sandbox.run_in_sandbox", fake_run)
    ctx = Context()
    ctx.use(SandboxService)
    result = ctx.sandbox.run("echo hi", timeout=5, workdir=".")
    assert result.stdout == "ok\n"
    assert calls[0][0] == "echo hi"
    assert calls[0][1]["timeout"] == 5


def test_current_uid_gid_posix(monkeypatch):
    """With os.getuid/getgid available, _current_uid_gid returns UID:GID."""
    import home_swe_home.sandbox as sandbox_mod

    monkeypatch.setattr(sandbox_mod.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(sandbox_mod.os, "getgid", lambda: 1000, raising=False)
    assert sandbox_mod._current_uid_gid() == "1000:1000"


def test_current_uid_gid_windows_fallback(monkeypatch):
    """Without os.getuid/getgid (Windows), _current_uid_gid returns ''."""
    import home_swe_home.sandbox as sandbox_mod

    monkeypatch.delattr(sandbox_mod.os, "getuid", raising=False)
    monkeypatch.delattr(sandbox_mod.os, "getgid", raising=False)
    assert sandbox_mod._current_uid_gid() == ""


def test_run_in_sandbox_returns_result(monkeypatch):
    calls = []

    def fake_run(cmd, *, capture_output, text, timeout):
        calls.append(cmd)
        return _completed(returncode=0, stdout="hello\n", stderr="")

    monkeypatch.setattr("home_swe_home.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox("echo hello", timeout=10)
    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.exit_code == 0
    assert result.timed_out is False
    assert calls[0][0] == "docker"
    assert calls[0][1] == "run"
    assert "--rm" in calls[0]


def test_run_in_sandbox_security_flags(monkeypatch):
    seen = {}

    def fake_run(cmd, *, capture_output, text, timeout):
        seen["cmd"] = cmd
        return _completed(returncode=0)

    monkeypatch.setattr("home_swe_home.sandbox.subprocess.run", fake_run)
    run_in_sandbox("echo hi")
    cmd = seen["cmd"]
    cmd_str = " ".join(cmd)
    assert "--network" in cmd and "none" in cmd
    assert "--read-only" in cmd
    from home_swe_home.sandbox import _current_uid_gid

    uid_gid = _current_uid_gid()
    if uid_gid:  # POSIX
        assert "--user" in cmd
        assert f"--user {uid_gid}" in cmd_str
    else:  # Windows: --user omitted
        assert "--user" not in cmd
    assert "--cap-drop" in cmd and "ALL" in cmd
    assert "--security-opt" in cmd and "no-new-privileges" in cmd
    assert "--memory" in cmd and "--memory-swap" in cmd
    assert "--cpus" in cmd
    assert "--pids-limit" in cmd
    assert "--tmpfs" in cmd and "noexec" in cmd_str
    assert "--rm" in cmd
    assert "--ulimit" in cmd and "nofile=256:256" in cmd_str
    assert "--ulimit" in cmd and "fsize=52428800" in cmd_str


def test_run_in_sandbox_workdir_confined_to_cwd(monkeypatch):
    """workdir escaping the CWD returns an error without calling docker."""
    seen = {}

    def fake_run(cmd, *, capture_output, text, timeout):
        seen["cmd"] = cmd
        return _completed(returncode=0)

    monkeypatch.setattr("home_swe_home.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox("echo x", workdir="/etc")
    assert result.exit_code == 1
    assert "outside the current working directory" in result.stderr
    assert "cmd" not in seen  # docker was never called


def test_run_in_sandbox_workdir_relative_ok(monkeypatch):
    """Relative workdir resolves under CWD and docker is called."""
    calls = []

    def fake_run(cmd, *, capture_output, text, timeout):
        calls.append(cmd)
        return _completed(returncode=0)

    monkeypatch.setattr("home_swe_home.sandbox.subprocess.run", fake_run)
    run_in_sandbox("echo x", workdir=".")
    v_idx = calls[0].index("-v")
    mount_spec = calls[0][v_idx + 1]
    assert mount_spec.endswith(":/workspace:rw")
    # Use removesuffix so a Windows drive letter (C:\...) is preserved.
    assert mount_spec.removesuffix(":/workspace:rw") == os.path.abspath(".")


def test_run_in_sandbox_docker_not_found(monkeypatch):
    """Missing docker CLI returns an error result (fail closed)."""

    def fake_run(cmd, *, capture_output, text, timeout):
        raise FileNotFoundError("docker")

    monkeypatch.setattr("home_swe_home.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox("echo hi")
    assert result.exit_code == 127
    assert "docker CLI not found" in result.stderr
    assert result.timed_out is False


def test_run_in_sandbox_timeout_kills_container(monkeypatch):
    kill_calls = []
    rm_calls = []
    call_count = {"n": 0}

    def fake_run(cmd, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise subprocess.TimeoutExpired(
                cmd, 1, output=b"partial output", stderr="stderr text"
            )
        if cmd[0] == "docker" and len(cmd) > 1 and cmd[1] in ("kill", "rm"):
            if cmd[1] == "kill":
                kill_calls.append(cmd)
            else:
                rm_calls.append(cmd)
            return SimpleNamespace(returncode=0)
        raise AssertionError(f"unexpected call: {cmd}")

    monkeypatch.setattr("home_swe_home.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox("sleep 100", timeout=1)
    assert result.timed_out is True
    assert result.exit_code == 124
    assert kill_calls, "expected docker kill to be attempted"
    assert rm_calls, "expected docker rm to be attempted"
    assert "partial output" in result.stdout
    assert "stderr text" in result.stderr


def test_run_in_sandbox_timeout_kill_respects_timeout(monkeypatch):
    """_kill_container passes a timeout to subprocess.run."""
    seen_kwargs = {}

    def fake_run(cmd, *args, **kwargs):
        if kwargs:
            seen_kwargs["timeout"] = kwargs.get("timeout")
        if cmd[0] == "docker" and len(cmd) > 1 and cmd[1] in ("kill", "rm"):
            return SimpleNamespace(returncode=0)
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr("home_swe_home.sandbox.subprocess.run", fake_run)
    run_in_sandbox("sleep 100", timeout=1)
    assert seen_kwargs.get("timeout") == 5  # KILL_TIMEOUT


def test_run_in_sandbox_timeout_none_output(monkeypatch):
    """TimeoutExpired with None stdout/stderr hits the None branch of _decode."""
    call_count = {"n": 0}

    def fake_run(cmd, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise subprocess.TimeoutExpired(cmd, 1, output=None, stderr=None)
        if cmd[0] == "docker" and len(cmd) > 1 and cmd[1] in ("kill", "rm"):
            return SimpleNamespace(returncode=0)
        raise AssertionError(f"unexpected call: {cmd}")

    monkeypatch.setattr("home_swe_home.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox("x", timeout=1)
    assert result.timed_out is True
    assert result.stdout == ""
    assert result.stderr == ""


def test_output_capped(monkeypatch):
    long_output = "x" * 20000

    def fake_run(cmd, *, capture_output, text, timeout):
        return _completed(returncode=0, stdout=long_output, stderr="")

    monkeypatch.setattr("home_swe_home.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox("echo long", timeout=10)
    assert len(result.stdout) <= 8192 + 60
    assert "capped" in result.stdout


def test_sandbox_result_dataclass():
    r = SandboxResult(stdout="o", stderr="e", exit_code=1, timed_out=False)
    assert r.stdout == "o"
    assert r.stderr == "e"
    assert r.exit_code == 1
    assert r.timed_out is False
