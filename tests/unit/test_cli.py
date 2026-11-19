"""Tests for home_swe_home.cli."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from home_swe_home.cli import DEFAULT_MODEL, _run_async, main
from home_swe_home.client import MiniClaudeError
from home_swe_home.core_loop import TurnInterrupted, TurnLimitReached


@pytest.mark.asyncio
async def test_main_no_api_key(monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with patch("home_swe_home.cli.load_dotenv"):
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
        patch("home_swe_home.cli.load_dotenv", side_effect=fake_load_dotenv),
        patch(
            "home_swe_home.core_loop.CoreLoopService.__call__",
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
        "home_swe_home.core_loop.CoreLoopService.__call__",
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
        "home_swe_home.core_loop.CoreLoopService.__call__",
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
        "home_swe_home.core_loop.CoreLoopService.__call__",
        new=fake_core_loop,
    ):
        code = await _run_async(["-p", "do something"])
    assert code == 1
    assert "home-swe-home: The model does not exist" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_main_headless_turn_limit_reached(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")

    async def fake_core_loop(*args, **kwargs):
        raise TurnLimitReached("Turn limit reached")

    with patch(
        "home_swe_home.core_loop.CoreLoopService.__call__",
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

    async def fake_repl(*, model, client=None, system_content=None, ctx=None, **kwargs):
        called.append(model)
        system_seen.append(system_content)

    with patch("home_swe_home.cli.run_repl", side_effect=fake_repl):
        code = await _run_async([])
    assert code == 0
    assert called == [DEFAULT_MODEL]
    assert system_seen[0] is not None
    assert "home-swe-home" in system_seen[0]


def test_main_wrapper(monkeypatch):
    """main() runs the async entry point via asyncio.run."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")

    async def fake_run_async(argv=None):
        return 0

    with patch("home_swe_home.cli._run_async", new=fake_run_async):
        code = main(["-p", "hello"])
    assert code == 0


@pytest.mark.asyncio
async def test_sandbox_flag_sets_env(monkeypatch):
    """--sandbox sets HOME_SWE_HOME_SANDBOX=1."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.delenv("HOME_SWE_HOME_SANDBOX", raising=False)

    seen = {}

    async def fake_run_headless(*, model, messages, **kwargs):
        seen["sandbox"] = __import__("os").environ.get("HOME_SWE_HOME_SANDBOX")
        return 0

    with (
        patch("home_swe_home.cli.load_dotenv"),  # avoid leaking .env into other tests
        patch("home_swe_home.cli._run_headless", new=fake_run_headless),
    ):
        code = await _run_async(["-p", "hello", "--sandbox"])
    assert code == 0
    assert seen["sandbox"] == "1"


@pytest.mark.asyncio
async def test_init_home_requires_repo(capsys):
    with patch("home_swe_home.cli.load_dotenv"):
        code = await _run_async(["--init-home", "/tmp/home"])
    assert code == 2
    assert "--home-repo" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_init_home_declined(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME_SWE_HOME_CONFIG_PATH", str(tmp_path / "none.json"))
    monkeypatch.setattr("home_swe_home.utils.home.CONFIG_PATH", tmp_path / "none.json")
    with (
        patch("home_swe_home.cli.load_dotenv"),
        patch("home_swe_home.cli.find_home", return_value=None),
        patch("home_swe_home.cli.input", return_value="n"),
        patch("home_swe_home.cli.run_wizard", return_value=False) as wizard,
    ):
        code = await _run_async(
            ["--init-home", str(tmp_path / "home"), "--home-repo", "org/home"]
        )
    assert code == 1
    assert wizard.called


@pytest.mark.asyncio
async def test_init_home_accepted(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME_SWE_HOME_CONFIG_PATH", str(tmp_path / "none.json"))
    with (
        patch("home_swe_home.cli.load_dotenv"),
        patch("home_swe_home.cli.find_home", return_value=None),
        patch("home_swe_home.cli.input", return_value="y"),
        patch("home_swe_home.cli.run_wizard", return_value=True) as wizard,
    ):
        code = await _run_async(
            ["--init-home", str(tmp_path / "home"), "--home-repo", "org/home"]
        )
    assert code == 0
    assert wizard.called


@pytest.mark.asyncio
async def test_model_default_from_env(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.setenv("HOME_SWE_HOME_MODEL", "gemini-2.5-flash")
    seen = {}

    async def fake_core_loop(*args, **kwargs):
        seen["model"] = kwargs.get("model")

    with patch("home_swe_home.core_loop.CoreLoopService.__call__", new=fake_core_loop):
        code = await _run_async(["-p", "hello"])
    assert code == 0
    assert seen["model"] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_show_events_flag_reaches_core_loop(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.delenv("HOME_SWE_HOME_SHOW_EVENTS", raising=False)
    seen = {}

    async def fake_core_loop(*args, **kwargs):
        seen["show_events"] = kwargs.get("show_events")

    with patch("home_swe_home.core_loop.CoreLoopService.__call__", new=fake_core_loop):
        code = await _run_async(["-p", "hello", "--show-events"])
    assert code == 0
    assert seen["show_events"] is True


@pytest.mark.asyncio
async def test_show_events_env_default(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.setenv("HOME_SWE_HOME_SHOW_EVENTS", "1")
    seen = {}

    async def fake_core_loop(*args, **kwargs):
        seen["show_events"] = kwargs.get("show_events")

    with patch("home_swe_home.core_loop.CoreLoopService.__call__", new=fake_core_loop):
        await _run_async(["-p", "hello"])
    assert seen["show_events"] is True


@pytest.mark.asyncio
async def test_init_home_guard_refuses_existing(monkeypatch, capsys):
    with (
        patch("home_swe_home.cli.load_dotenv"),
        patch("home_swe_home.cli.find_home", return_value=Path("/home/agents-home")),
        patch("home_swe_home.cli.run_wizard") as wizard,
    ):
        code = await _run_async(["--init-home", "/tmp/home", "--home-repo", "org/home"])
    assert code == 2
    assert not wizard.called
    assert "already exists" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_init_home_plan_is_non_mutating(monkeypatch, capsys, tmp_path):
    with (
        patch("home_swe_home.cli.load_dotenv"),
        patch("home_swe_home.cli.run_wizard") as wizard,
    ):
        code = await _run_async(
            [
                "--init-home",
                str(tmp_path / "home"),
                "--home-repo",
                "org/home",
                "--plan",
                "--json",
            ]
        )
    assert code == 0
    assert not wizard.called
    assert json.loads(capsys.readouterr().out)["repo"] == "org/home"


@pytest.mark.asyncio
async def test_init_home_yes_flag_skips_input(monkeypatch, tmp_path):
    with (
        patch("home_swe_home.cli.load_dotenv"),
        patch("home_swe_home.cli.find_home", return_value=None),
        patch("home_swe_home.cli.input") as prompt,
        patch("home_swe_home.cli.run_wizard", return_value=True),
    ):
        code = await _run_async(
            ["--init-home", str(tmp_path / "home"), "--home-repo", "org/home", "--yes"]
        )
    assert code == 0
    assert not prompt.called


@pytest.mark.asyncio
async def test_init_home_plain_plan_output(monkeypatch, capsys, tmp_path):
    with patch("home_swe_home.cli.load_dotenv"):
        code = await _run_async(
            ["--init-home", str(tmp_path / "home"), "--home-repo", "org/home", "--plan"]
        )
    assert code == 0
    assert "repo: org/home" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_init_home_json_result(monkeypatch, capsys, tmp_path):
    with (
        patch("home_swe_home.cli.load_dotenv"),
        patch("home_swe_home.cli.find_home", return_value=None),
        patch("home_swe_home.cli.input", return_value="y"),
        patch("home_swe_home.cli.run_wizard", return_value=True),
    ):
        code = await _run_async(
            ["--init-home", str(tmp_path / "home"), "--home-repo", "org/home", "--json"]
        )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["accepted"] is True


@pytest.mark.asyncio
async def test_init_home_force_bypasses_guard(monkeypatch, tmp_path):
    with (
        patch("home_swe_home.cli.load_dotenv"),
        patch("home_swe_home.cli.find_home", return_value=None),
        patch("home_swe_home.cli.input", return_value="y"),
        patch("home_swe_home.cli.run_wizard", return_value=True) as wizard,
    ):
        code = await _run_async(
            [
                "--init-home",
                str(tmp_path / "home"),
                "--home-repo",
                "org/home",
                "--force",
                "--yes",
            ]
        )
    assert code == 0 and wizard.called
