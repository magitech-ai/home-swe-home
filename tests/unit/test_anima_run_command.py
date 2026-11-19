"""Tests for the anima RunCommandService component."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest
from anima import Context

from home_swe_home.sandbox import SandboxResult, SandboxService
from home_swe_home.tools.run_command import RunCommandService


@pytest.mark.asyncio
async def test_run_command_service_mounts_and_is_accessible():
    """RunCommandService mounts on a Context and is accessible as ctx.run_command."""
    ctx = Context()
    ctx.use(RunCommandService)
    await ctx.flush()
    assert hasattr(ctx, "run_command")
    assert ctx.run_command is not None
    assert isinstance(ctx.run_command, RunCommandService)
    assert ctx.run_command.name == "run_command"


@pytest.mark.asyncio
async def test_run_command_service_host_default(monkeypatch):
    """run_command runs on the host by default (no sandbox)."""
    monkeypatch.delenv("HOME_SWE_HOME_SANDBOX", raising=False)

    calls = []

    def fake_run(cmd, *, capture_output, text, timeout):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="out\n", stderr="err\n")

    monkeypatch.setattr("subprocess.run", fake_run)

    ctx = Context()
    ctx.use(RunCommandService)
    await ctx.flush()

    result = ctx.run_command(command="echo out; echo err >&2", timeout=10)
    assert "stdout:\nout\n" in result
    assert "stderr:\nerr\n" in result
    assert "exit code: 0" in result
    assert calls[0] == ["echo", "out;", "echo", "err", ">&2"]


@pytest.mark.asyncio
async def test_run_command_service_host_timeout(monkeypatch):
    """Host execution handles subprocess timeout."""
    monkeypatch.delenv("HOME_SWE_HOME_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr("subprocess.run", fake_run)

    ctx = Context()
    ctx.use(RunCommandService)
    await ctx.flush()

    result = ctx.run_command(command="sleep 10", timeout=1)
    assert "exit code: 124" in result
    assert "timed out" in result


@pytest.mark.asyncio
async def test_run_command_service_host_command_not_found(monkeypatch):
    """Host execution reports missing commands clearly."""
    monkeypatch.delenv("HOME_SWE_HOME_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        raise FileNotFoundError("no such file")

    monkeypatch.setattr("subprocess.run", fake_run)

    ctx = Context()
    ctx.use(RunCommandService)
    await ctx.flush()

    result = ctx.run_command(command="no_such_cmd", timeout=10)
    assert "command not found" in result.lower()


@pytest.mark.asyncio
async def test_run_command_service_sandbox_opt_in_env(monkeypatch):
    """HOME_SWE_HOME_SANDBOX=1 routes to the Docker sandbox."""
    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "1")

    ctx = Context()
    ctx.use(RunCommandService)
    ctx.use(SandboxService)
    await ctx.flush()
    ctx.sandbox.run = lambda command, **kw: SandboxResult(  # type: ignore[attr-defined]
        stdout="sandboxed\n", stderr="", exit_code=0, timed_out=False
    )

    result = ctx.run_command(command="echo hi", timeout=10)
    assert "sandboxed" in result
    assert "exit code: 0" in result


@pytest.mark.asyncio
async def test_run_command_service_host_timeout_with_output(monkeypatch):
    """Host timeout includes stdout and stderr when present."""
    monkeypatch.delenv("HOME_SWE_HOME_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(
            cmd, 1, output=b"partial out", stderr="partial err"
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    ctx = Context()
    ctx.use(RunCommandService)
    await ctx.flush()

    result = ctx.run_command(command="sleep 10", timeout=1)
    assert "partial out" in result
    assert "partial err" in result
    assert "exit code: 124" in result
    assert "timed out" in result


@pytest.mark.asyncio
async def test_run_command_service_host_stdout_only(monkeypatch):
    """Host execution with stdout but no stderr."""
    monkeypatch.delenv("HOME_SWE_HOME_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        return SimpleNamespace(returncode=0, stdout="just stdout\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    ctx = Context()
    ctx.use(RunCommandService)
    await ctx.flush()

    result = ctx.run_command(command="echo just stdout", timeout=10)
    assert "stdout:\njust stdout\n" in result
    assert "stderr:" not in result
    assert "exit code: 0" in result


@pytest.mark.asyncio
async def test_run_command_service_host_stderr_only(monkeypatch):
    """Host execution with stderr but no stdout."""
    monkeypatch.delenv("HOME_SWE_HOME_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        return SimpleNamespace(returncode=1, stdout="", stderr="oops\n")

    monkeypatch.setattr("subprocess.run", fake_run)

    ctx = Context()
    ctx.use(RunCommandService)
    await ctx.flush()

    result = ctx.run_command(command="false", timeout=10)
    assert "stdout:" not in result
    assert "stderr:\noops\n" in result
    assert "exit code: 1" in result


@pytest.mark.asyncio
async def test_run_command_service_sandbox_with_stderr_and_timeout(monkeypatch):
    """Sandbox mode passes through stderr and timed_out flag."""
    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "1")

    ctx = Context()
    ctx.use(RunCommandService)
    ctx.use(SandboxService)
    await ctx.flush()
    ctx.sandbox.run = lambda command, **kw: SandboxResult(  # type: ignore[attr-defined]
        stdout="", stderr="sandbox err", exit_code=1, timed_out=True
    )

    result = ctx.run_command(command="bad cmd", timeout=10)
    assert "sandbox err" in result
    assert "exit code: 1" in result
    assert "timed out" in result


@pytest.mark.asyncio
async def test_run_command_service_is_singleton_per_context():
    """Mounting twice returns the same service instance."""
    ctx = Context()
    ctx.use(RunCommandService)
    ctx.use(RunCommandService)
    await ctx.flush()
    assert ctx.run_command is ctx.run_command
