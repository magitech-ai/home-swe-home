"""Tests for magecode.cli."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from magecode.cli import DEFAULT_MODEL, _run_async, main
from magecode.client import MiniClaudeError
from magecode.core_loop import TurnInterrupted, TurnLimitReached


@pytest.mark.asyncio
async def test_main_no_api_key(monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with patch("magecode.cli.load_dotenv"):
        code = await _run_async(["-p", "say hi in three words"])
    assert code == 2
    stderr = capsys.readouterr().err
    assert "NVIDIA_API_KEY" in stderr
    assert "nvapi-" not in stderr  # the key must never be printed


@pytest.mark.asyncio
async def test_main_dotenv_fallback(monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    def fake_load_dotenv(*args, **kwargs):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-from-dotenv")

    async def fake_core_loop(*args, **kwargs):
        print("hello there friend")

    with (
        patch("magecode.cli.load_dotenv", side_effect=fake_load_dotenv),
        patch(
            "magecode.core_loop.CoreLoopService.__call__",
            new=fake_core_loop,
        ),
    ):
        code = await _run_async(["-p", "say hi in three words"])
    assert code == 0


@pytest.mark.asyncio
async def test_main_headless_runs_one_turn(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    seen = {}

    async def fake_core_loop(*args, **kwargs):
        seen["model"] = kwargs.get("model")
        seen["messages"] = kwargs.get("messages")
        print("hello there friend")

    with patch(
        "magecode.core_loop.CoreLoopService.__call__",
        new=fake_core_loop,
    ):
        code = await _run_async(
            ["-p", "say hi in three words", "--model", "meta/llama-3.1-8b-instruct"]
        )
    assert code == 0
    assert seen["model"] == "meta/llama-3.1-8b-instruct"
    assert seen["messages"][0]["role"] == "system"
    assert seen["messages"][1] == {
        "role": "user",
        "content": "say hi in three words",
    }


@pytest.mark.asyncio
async def test_main_headless_interrupted(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")

    async def fake_core_loop(*args, **kwargs):
        raise TurnInterrupted()

    with patch(
        "magecode.core_loop.CoreLoopService.__call__",
        new=fake_core_loop,
    ):
        code = await _run_async(["-p", "do something"])
    assert code == 130
    assert "Turn interrupted." in capsys.readouterr().err


@pytest.mark.asyncio
async def test_main_headless_api_error(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")

    async def fake_core_loop(*args, **kwargs):
        raise MiniClaudeError("The model does not exist")

    with patch(
        "magecode.core_loop.CoreLoopService.__call__",
        new=fake_core_loop,
    ):
        code = await _run_async(["-p", "do something"])
    assert code == 1
    assert "magecode: The model does not exist" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_main_headless_turn_limit_reached(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")

    async def fake_core_loop(*args, **kwargs):
        raise TurnLimitReached("Turn limit reached")

    with patch(
        "magecode.core_loop.CoreLoopService.__call__",
        new=fake_core_loop,
    ):
        code = await _run_async(["-p", "do something"])
    assert code == 1
    assert "Turn limit reached" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_main_interactive(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    called = []
    system_seen = []

    async def fake_repl(*, model, client=None, system_content=None, ctx=None):
        called.append(model)
        system_seen.append(system_content)

    with patch("magecode.cli.run_repl", side_effect=fake_repl):
        code = await _run_async([])
    assert code == 0
    assert called == [DEFAULT_MODEL]
    assert system_seen[0] is not None
    assert "magecode" in system_seen[0]


def test_main_wrapper(monkeypatch):
    """main() runs the async entry point via asyncio.run."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")

    async def fake_run_async(argv=None):
        return 0

    with patch("magecode.cli._run_async", new=fake_run_async):
        code = main(["-p", "hello"])
    assert code == 0


@pytest.mark.asyncio
async def test_sandbox_flag_sets_env(monkeypatch):
    """--sandbox sets MAGECODE_SANDBOX=1."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.delenv("MAGECODE_SANDBOX", raising=False)

    seen = {}

    async def fake_run_headless(*, model, messages):
        seen["sandbox"] = __import__("os").environ.get("MAGECODE_SANDBOX")
        return 0

    with (
        patch("magecode.cli.load_dotenv"),  # avoid leaking .env into other tests
        patch("magecode.cli._run_headless", new=fake_run_headless),
    ):
        code = await _run_async(["-p", "hello", "--sandbox"])
    assert code == 0
    assert seen["sandbox"] == "1"


@pytest.mark.asyncio
async def test_init_home_requires_repo(capsys):
    with patch("magecode.cli.load_dotenv"):
        code = await _run_async(["--init-home", "/tmp/home"])
    assert code == 2
    assert "--home-repo" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_init_home_declined(monkeypatch):
    with (
        patch("magecode.cli.load_dotenv"),
        patch("magecode.cli.input", return_value="n"),
        patch("magecode.cli.run_wizard", return_value=False) as wizard,
    ):
        code = await _run_async(["--init-home", "/tmp/home", "--home-repo", "org/home"])
    assert code == 1
    assert wizard.called


@pytest.mark.asyncio
async def test_init_home_accepted(monkeypatch):
    with (
        patch("magecode.cli.load_dotenv"),
        patch("magecode.cli.input", return_value="y"),
        patch("magecode.cli.run_wizard", return_value=True) as wizard,
    ):
        code = await _run_async(["--init-home", "/tmp/home", "--home-repo", "org/home"])
    assert code == 0
    assert wizard.called


@pytest.mark.asyncio
async def test_model_default_from_env(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.setenv("MAGECODE_MODEL", "gemini-2.5-flash")
    seen = {}

    async def fake_core_loop(*args, **kwargs):
        seen["model"] = kwargs.get("model")

    with patch("magecode.core_loop.CoreLoopService.__call__", new=fake_core_loop):
        code = await _run_async(["-p", "hello"])
    assert code == 0
    assert seen["model"] == "gemini-2.5-flash"
