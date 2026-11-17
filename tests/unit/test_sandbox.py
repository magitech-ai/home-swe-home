"""Tests for magecode.sandbox."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

from magecode.sandbox import SandboxResult, run_in_sandbox


def _completed(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_in_sandbox_returns_result(monkeypatch):
    calls = []

    def fake_run(cmd, *, capture_output, text, timeout):
        calls.append(cmd)
        return _completed(returncode=0, stdout="hello\n", stderr="")

    monkeypatch.setattr("magecode.sandbox.subprocess.run", fake_run)
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

    monkeypatch.setattr("magecode.sandbox.subprocess.run", fake_run)
    run_in_sandbox("echo hi")
    cmd = seen["cmd"]
    cmd_str = " ".join(cmd)
    assert "--network" in cmd and "none" in cmd
    assert "--read-only" in cmd
    assert "--user" in cmd and "65534:65534" in cmd
    assert "--cap-drop" in cmd and "ALL" in cmd
    assert "--security-opt" in cmd and "no-new-privileges" in cmd
    assert "--memory" in cmd and "--memory-swap" in cmd
    assert "--cpus" in cmd
    assert "--pids-limit" in cmd
    assert "--tmpfs" in cmd and "noexec" in cmd_str
    assert "--rm" in cmd


def test_run_in_sandbox_timeout_kills_container(monkeypatch):
    kill_calls = []
    rm_calls = []
    call_count = {"n": 0}

    def fake_run(cmd, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call: docker run times out with mixed stdout/stderr types
            raise subprocess.TimeoutExpired(
                cmd, 1, output=b"partial output", stderr="stderr text"
            )
        # Subsequent calls: docker kill / rm succeed
        if cmd[0] == "docker" and len(cmd) > 1 and cmd[1] in ("kill", "rm"):
            if cmd[1] == "kill":
                kill_calls.append(cmd)
            else:
                rm_calls.append(cmd)
            return SimpleNamespace(returncode=0)
        raise AssertionError(f"unexpected call: {cmd}")

    monkeypatch.setattr("magecode.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox("sleep 100", timeout=1)
    assert result.timed_out is True
    assert result.exit_code == 124
    assert kill_calls, "expected docker kill to be attempted"
    assert rm_calls, "expected docker rm to be attempted"
    assert "partial output" in result.stdout  # bytes decoded
    assert "stderr text" in result.stderr  # str passed through


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

    monkeypatch.setattr("magecode.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox("x", timeout=1)
    assert result.timed_out is True
    assert result.stdout == ""
    assert result.stderr == ""


def test_output_capped(monkeypatch):
    long_output = "x" * 20000

    def fake_run(cmd, *, capture_output, text, timeout):
        return _completed(returncode=0, stdout=long_output, stderr="")

    monkeypatch.setattr("magecode.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox("echo long", timeout=10)
    assert len(result.stdout) <= 8192 + 60  # cap + message
    assert "capped" in result.stdout


def test_sandbox_result_dataclass():
    r = SandboxResult(stdout="o", stderr="e", exit_code=1, timed_out=False)
    assert r.stdout == "o"
    assert r.stderr == "e"
    assert r.exit_code == 1
    assert r.timed_out is False
