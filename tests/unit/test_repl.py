"""Tests for mini_claude.repl."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from mini_claude.client import MiniClaudeError
from mini_claude.repl import _show_context, run_repl
from mini_claude.turn import TurnInterrupted


class FakeClient:
    pass


def test_repl_exits_on_eof(capsys):
    with patch("mini_claude.repl.input", side_effect=EOFError):
        run_repl(model="m", client=FakeClient())
    out = capsys.readouterr().out
    assert "mini-claude interactive chat" in out


def test_repl_keyboard_interrupt_continues(capsys):
    with patch(
        "mini_claude.repl.input",
        side_effect=[KeyboardInterrupt, EOFError],
    ):
        run_repl(model="m", client=FakeClient())
    assert "Turn interrupted" not in capsys.readouterr().out


def test_repl_model_switch(capsys):
    with patch("mini_claude.repl.input", side_effect=["/model other/model", EOFError]):
        run_repl(model="m", client=FakeClient())
    out = capsys.readouterr().out
    assert "model: m" in out
    assert "model: other/model" in out


def test_repl_model_command_without_id_shows_current(capsys):
    with patch("mini_claude.repl.input", side_effect=["/model", EOFError]):
        run_repl(model="m", client=FakeClient())
    assert capsys.readouterr().out.count("model: m") == 2


def test_repl_blank_lines_are_ignored():
    with patch("mini_claude.repl.input") as mock_input:
        mock_input.side_effect = ["   ", "", EOFError]
        run_repl(model="m", client=FakeClient())
    assert mock_input.call_count == 3


def test_repl_turn_interrupted_is_swallowed(capsys):
    with (
        patch("mini_claude.repl.input", side_effect=["say hi", EOFError]),
        patch("mini_claude.repl.run_turn", side_effect=TurnInterrupted()),
    ):
        run_repl(model="m", client=FakeClient())
    assert "Turn interrupted." in capsys.readouterr().out


def test_repl_api_error_prints_and_continues(capsys):
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


def test_repl_context_command(capsys):
    with patch(
        "mini_claude.repl.input",
        side_effect=["/context", EOFError],
    ):
        run_repl(model="m", client=FakeClient())
    out = capsys.readouterr().out
    assert "context window" in out
    assert "tokens" in out
    assert "[0] system" in out


def test_repl_user_message_reaches_turn():
    seen = {}

    def capture_turn(*, model, messages, client=None, reply_prefix="", max_turns=20):
        seen["messages"] = messages
        seen["model"] = model
        seen["reply_prefix"] = reply_prefix
        seen["max_turns"] = max_turns

    with (
        patch("mini_claude.repl.input", side_effect=["hello world", EOFError]),
        patch("mini_claude.repl.run_turn", side_effect=capture_turn),
    ):
        run_repl(model="m", client=FakeClient())
    assert seen["model"] == "m"
    assert seen["messages"][0]["role"] == "system"
    assert seen["messages"][1] == {
        "role": "user",
        "content": "hello world",
    }
    assert seen["reply_prefix"] == "< "
    assert seen["max_turns"] == 20


def test_repl_turn_limit_reached(capsys):
    """REPL should report TurnLimitReached error when run_turn raises it."""
    from mini_claude.turn import TurnLimitReached

    def capture_turn(*, model, messages, client=None, reply_prefix="", max_turns=20):
        raise TurnLimitReached("Turn limit reached")

    with (
        patch("mini_claude.repl.input", side_effect=["hello world", EOFError]),
        patch("mini_claude.repl.run_turn", side_effect=capture_turn),
    ):
        run_repl(model="m", client=FakeClient())
    out = capsys.readouterr().out
    assert "Turn limit reached" in out


def test_repl_context_shows_tool_calls(capsys):
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "You are mini-claude."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "x.txt"}',
                    },
                }
            ],
        },
    ]
    _show_context(messages)
    out = capsys.readouterr().out
    assert "context window" in out
    assert "[0] system" in out
    assert "[1] assistant (1 tool call(s))" in out
    assert "tool: read_file" in out
