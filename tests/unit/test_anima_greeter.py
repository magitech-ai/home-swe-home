"""Tests for the anima GreeterService component (dependency injection demo)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from anima import Context

from magecode.anima_greeter import GreeterService, mount_greeter
from magecode.tools.run_command import RunCommandService


@pytest.mark.asyncio
async def test_greeter_service_mounts_after_run_command():
    """Greeter mounts only after run_command is available (dependency injection)."""
    ctx = Context()
    ctx.use(RunCommandService)
    ctx.use(GreeterService)
    await ctx.flush()

    assert hasattr(ctx, "greeter")
    assert isinstance(ctx.greeter, GreeterService)
    assert ctx.greeter.name == "greeter"


@pytest.mark.asyncio
async def test_greeter_uses_injected_run_command(monkeypatch):
    """Greeter delegates to the injected run_command service."""
    monkeypatch.delenv("MAGECODE_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        assert cmd == ["whoami"]
        return SimpleNamespace(returncode=0, stdout="alice\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    ctx = Context()
    ctx.use(RunCommandService)
    ctx.use(GreeterService)
    await ctx.flush()

    result = ctx.greeter.greet()
    assert "alice" in result
    assert "greeter" in result


@pytest.mark.asyncio
async def test_greeter_fallback_unknown_username(monkeypatch):
    """Greeter falls back to 'unknown' when whoami output has no name."""
    monkeypatch.delenv("MAGECODE_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        return SimpleNamespace(
            returncode=0, stdout="stdout:\n\nexit code: 0", stderr=""
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    ctx = Context()
    ctx.use(RunCommandService)
    ctx.use(GreeterService)
    await ctx.flush()

    result = ctx.greeter.greet()
    assert "unknown" in result


@pytest.mark.asyncio
async def test_greeter_fails_without_run_command():
    """Greeter cannot be accessed without its run_command dependency."""
    ctx = Context()
    ctx.use(GreeterService)
    await ctx.flush()

    # greeter's dependency (run_command) is missing, so accessing it raises
    with pytest.raises(AttributeError, match="Service 'greeter' is not registered"):
        _ = ctx.greeter


@pytest.mark.asyncio
async def test_greeter_mount_helper():
    """mount_greeter() helper registers both greeter and run_command."""
    ctx = Context()
    mount_greeter(ctx)
    await ctx.flush()
    assert hasattr(ctx, "greeter")
    assert hasattr(ctx, "run_command")
    assert isinstance(ctx.greeter, GreeterService)
    assert isinstance(ctx.run_command, RunCommandService)
