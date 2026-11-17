"""Tests for mini_claude.repl."""

from __future__ import annotations

from unittest.mock import patch

from mini_claude.client import MiniClaudeError
from mini_claude.repl import run_repl
from mini_claude.turn import TurnInterrupted


def inputs(*sequence):
    iterator = iter(sequence)

    def next_input(prompt=""):
        return next(iterator)

    return next_input


def test_repl_exits_on_eof(capsys):
    class FakeClient:
        pass

    with patch("mini_claude.repl.input", side_effect=EOFError):
        run_repl(model="m", client=FakeClient())
    out = capsys.readouterr().out
    assert "mini-claude interactive chat" in out


def test_repl_keyboard_interrupt_continues(capsys):
    class FakeClient:
        pass

    with patch(
        "mini_claude.repl.input",
        side_effect=[KeyboardInterrupt, EOFError],
    ):
        run_repl(model="m", client=FakeClient())
    assert "Turn interrupted" not in capsys.readouterr().out


def test_repl_model_switch(capsys):
    class FakeClient:
        pass

    with patch("mini_claude.repl.input", side_effect=["/model other/model", EOFError]):
        run_repl(model="m", client=FakeClient())
    out = capsys.readouterr().out
    assert "model: m" in out
    assert "model: other/model" in out


def test_repl_model_command_without_id_shows_current(capsys):
    class FakeClient:
        pass

    with patch("mini_claude.repl.input", side_effect=["/model", EOFError]):
        run_repl(model="m", client=FakeClient())
    assert capsys.readouterr().out.count("model: m") == 2


def test_repl_blank_lines_are_ignored():
    class FakeClient:
        pass

    with patch("mini_claude.repl.input") as mock_input:
        mock_input.side_effect = ["   ", "", EOFError]
        run_repl(model="m", client=FakeClient())
    assert mock_input.call_count == 3


def test_repl_turn_interrupted_is_swallowed(capsys):
    class FakeClient:
        pass

    with (
        patch("mini_claude.repl.input", side_effect=["say hi", EOFError]),
        patch("mini_claude.repl.run_turn", side_effect=TurnInterrupted()),
    ):
        run_repl(model="m", client=FakeClient())
    assert "Turn interrupted." in capsys.readouterr().out


def test_repl_api_error_prints_and_continues(capsys):
    class FakeClient:
        pass

    with (
        patch("mini_claude.repl.input", side_effect=["say hi", EOFError]),
        patch(
            "mini_claude.repl.run_turn",
            side_effect=MiniClaudeError("The model does not exist"),
        ),
    ):
        run_repl(model="m", client=FakeClient())
    out = capsys.readouterr().out
    assert "mini-claude: The model does not exist" in out


def test_repl_user_message_reaches_turn():
    class FakeClient:
        pass

    seen = {}

    def capture_turn(*, model, messages, client=None):
        seen["messages"] = messages
        seen["model"] = model

    with (
        patch("mini_claude.repl.input", side_effect=["hello world", EOFError]),
        patch("mini_claude.repl.run_turn", side_effect=capture_turn),
    ):
        run_repl(model="m", client=FakeClient())
    assert seen["model"] == "m"
    assert seen["messages"] == [{"role": "user", "content": "hello world"}]
