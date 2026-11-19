"""Tests for magecode.repl."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from anima import Context

from magecode.client import MiniClaudeError
from magecode.context import AGENT_SERVICES
from magecode.core_loop import TurnInterrupted, TurnLimitReached
from magecode.repl import _show_context, run_repl


class FakeCoreLoop:
    """A fake CoreLoopService that raises a given exception when called."""

    name = "core_loop"

    def __init__(self, side_effect):
        self._side_effect = side_effect
        self._capture = None

    async def __call__(self, **kwargs):
        if self._capture is not None:
            return await self._capture(**kwargs)
        raise self._side_effect


async def _build_context(with_core_loop: bool = True) -> Context:
    ctx = Context()
    from magecode.core_loop import CoreLoopService

    for service_cls in AGENT_SERVICES:
        if service_cls is not CoreLoopService or with_core_loop:
            ctx.use(service_cls)
    await ctx.flush()
    return ctx


async def _build_context_with_fake(side_effect) -> Context:
    ctx = Context()
    from magecode.core_loop import CoreLoopService

    for service_cls in AGENT_SERVICES:
        if service_cls is not CoreLoopService:
            ctx.use(service_cls)
    ctx.reflect.provide("core_loop", FakeCoreLoop(side_effect))
    await ctx.flush()
    return ctx


class FakeClient:
    pass


@pytest.mark.asyncio
async def test_repl_exits_on_eof(capsys):
    ctx = await _build_context()
    with patch("magecode.repl.input", side_effect=EOFError):
        await run_repl(model="m", ctx=ctx)
    out = capsys.readouterr().out
    assert "magecode interactive chat" in out


@pytest.mark.asyncio
async def test_repl_keyboard_interrupt_continues(capsys):
    ctx = await _build_context()
    with patch(
        "magecode.repl.input",
        side_effect=[KeyboardInterrupt, EOFError],
    ):
        await run_repl(model="m", ctx=ctx)
    assert "Turn interrupted" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_repl_model_switch(capsys):
    ctx = await _build_context()
    with patch("magecode.repl.input", side_effect=["/model other/model", EOFError]):
        await run_repl(model="m", ctx=ctx)
    out = capsys.readouterr().out
    assert "model: m" in out
    assert "model: other/model" in out


@pytest.mark.asyncio
async def test_repl_model_command_without_id_shows_current(capsys):
    ctx = await _build_context()
    with patch("magecode.repl.input", side_effect=["/model", EOFError]):
        await run_repl(model="m", ctx=ctx)
    assert capsys.readouterr().out.count("model: m") == 2


@pytest.mark.asyncio
async def test_repl_blank_lines_are_ignored():
    ctx = await _build_context()
    with patch("magecode.repl.input") as mock_input:
        mock_input.side_effect = ["   ", "", EOFError]
        await run_repl(model="m", ctx=ctx)
    assert mock_input.call_count == 3


@pytest.mark.asyncio
async def test_repl_turn_interrupted_is_swallowed(capsys):
    ctx = await _build_context_with_fake(TurnInterrupted())
    with patch("magecode.repl.input", side_effect=["say hi", EOFError]):
        await run_repl(model="m", ctx=ctx)
    assert "Turn interrupted." in capsys.readouterr().out


@pytest.mark.asyncio
async def test_repl_api_error_prints_and_continues(capsys):
    ctx = await _build_context_with_fake(MiniClaudeError("The model does not exist"))
    with patch("magecode.repl.input", side_effect=["say hi", EOFError]):
        await run_repl(model="m", ctx=ctx)
    out = capsys.readouterr().out
    assert "magecode: The model does not exist" in out


@pytest.mark.asyncio
async def test_repl_skill_command_prints_skill(monkeypatch, capsys):
    ctx = await _build_context()
    monkeypatch.setattr(ctx.skills, "load", lambda name: f"SKILL BODY: {name}")
    with patch("magecode.repl.input", side_effect=["/skill tdd", EOFError]):
        await run_repl(model="m", ctx=ctx)
    assert "SKILL BODY: tdd" in capsys.readouterr().out


async def test_repl_context_command(capsys):
    ctx = await _build_context()
    with patch(
        "magecode.repl.input",
        side_effect=["/context", EOFError],
    ):
        await run_repl(model="m", ctx=ctx)
    out = capsys.readouterr().out
    assert "context window" in out
    assert "tokens" in out
    assert "[0] system" in out


@pytest.mark.asyncio
async def test_repl_user_message_reaches_turn():
    ctx = await _build_context()
    seen = {}

    async def capture_turn(
        *,
        model: str,
        messages: list,
        client: Any = None,
        reply_prefix: str = "",
        max_turns: int = 20,
        stream: bool = False,
        show_reasoning: bool = False,
        show_events: bool = False,
        effort: str = "medium",
    ):
        seen["messages"] = messages
        seen["model"] = model
        seen["reply_prefix"] = reply_prefix
        seen["max_turns"] = max_turns

    # Replace CoreLoopService with a fake that captures the call
    fake = FakeCoreLoop(None)
    fake._capture = capture_turn
    ctx.reflect.provide("core_loop", fake)
    await ctx.flush()

    with patch("magecode.repl.input", side_effect=["hello world", EOFError]):
        await run_repl(model="m", ctx=ctx)
    assert seen["model"] == "m"
    assert seen["messages"][0]["role"] == "system"
    assert seen["messages"][1] == {
        "role": "user",
        "content": "hello world",
    }
    assert seen["reply_prefix"] == "< "
    assert seen["max_turns"] == 20


@pytest.mark.asyncio
async def test_repl_turn_limit_reached(capsys):
    """REPL should report TurnLimitReached error when run_core_loop raises it."""
    ctx = await _build_context_with_fake(TurnLimitReached("Turn limit reached"))
    with patch("magecode.repl.input", side_effect=["hello world", EOFError]):
        await run_repl(model="m", ctx=ctx)
    out = capsys.readouterr().out
    assert "Turn limit reached" in out


@pytest.mark.asyncio
async def test_repl_context_shows_tool_calls(capsys):
    ctx = await _build_context()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "You are magecode."},
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
    _show_context(messages, ctx)
    out = capsys.readouterr().out
    assert "context window" in out
    assert "[0] system" in out
    assert "[1] assistant (1 tool call(s))" in out
    assert "tool: read_file" in out
