"""Tests for mini_claude.cli."""

from __future__ import annotations

from unittest.mock import patch

from mini_claude.cli import DEFAULT_MODEL, main
from mini_claude.client import MiniClaudeError
from mini_claude.core_loop import TurnInterrupted, TurnLimitReached


def test_main_no_api_key(monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with patch("mini_claude.cli.load_dotenv"):
        code = main(["-p", "say hi in three words"])
    assert code == 2
    stderr = capsys.readouterr().err
    assert "NVIDIA_API_KEY" in stderr
    assert "nvapi-" not in stderr  # the key must never be printed


def test_main_dotenv_fallback(monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    def fake_load_dotenv(*args, **kwargs):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-from-dotenv")

    def fake_core_loop(*, model, messages, client=None):
        print("hello there friend")

    with (
        patch("mini_claude.cli.load_dotenv", side_effect=fake_load_dotenv),
        patch("mini_claude.cli.run_core_loop", side_effect=fake_core_loop),
    ):
        code = main(["-p", "say hi in three words"])
    assert code == 0


def test_main_headless_runs_one_turn(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    seen = {}

    def fake_core_loop(*, model, messages, client=None):
        seen["model"] = model
        seen["messages"] = messages
        print("hello there friend")

    with patch("mini_claude.cli.run_core_loop", side_effect=fake_core_loop):
        code = main(
            ["-p", "say hi in three words", "--model", "meta/llama-3.1-8b-instruct"]
        )
    assert code == 0
    assert seen["model"] == "meta/llama-3.1-8b-instruct"
    assert seen["messages"][0]["role"] == "system"
    assert seen["messages"][1] == {
        "role": "user",
        "content": "say hi in three words",
    }


def test_main_headless_interrupted(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")

    def fake_core_loop(**kwargs):
        raise TurnInterrupted()

    with patch("mini_claude.cli.run_core_loop", side_effect=fake_core_loop):
        code = main(["-p", "do something"])
    assert code == 130
    assert "Turn interrupted." in capsys.readouterr().err


def test_main_headless_api_error(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")

    def fake_core_loop(**kwargs):
        raise MiniClaudeError("The model does not exist")

    with patch("mini_claude.cli.run_core_loop", side_effect=fake_core_loop):
        code = main(["-p", "do something"])
    assert code == 1
    assert "mini-claude: The model does not exist" in capsys.readouterr().err


def test_main_headless_turn_limit_reached(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")

    def fake_core_loop(**kwargs):
        raise TurnLimitReached("Turn limit reached")

    with patch("mini_claude.cli.run_core_loop", side_effect=fake_core_loop):
        code = main(["-p", "do something"])
    assert code == 1
    assert "Turn limit reached" in capsys.readouterr().err


def test_main_interactive(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    called = []
    system_seen = []

    def fake_repl(*, model, client=None, system_content=None):
        called.append(model)
        system_seen.append(system_content)

    with patch("mini_claude.cli.run_repl", side_effect=fake_repl):
        code = main([])
    assert code == 0
    assert called == [DEFAULT_MODEL]
    assert system_seen[0] is not None
    assert "mini-claude" in system_seen[0]
