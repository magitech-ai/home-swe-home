"""Tests for the REPL module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from home_swe_home.repl import _show_context, _text_preview, run_repl


@pytest.mark.asyncio
async def test_repl_exit_on_eof(capsys: pytest.CaptureFixture) -> None:
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={
            "agent": MagicMock(),
            "dispose": AsyncMock(),
        }
    )
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=EOFError):
            await run_repl(model="m")

    captured = capsys.readouterr().out
    assert "home-swe-home interactive chat" in captured


@pytest.mark.asyncio
async def test_repl_model_command(capsys: pytest.CaptureFixture) -> None:
    mock_agent = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": mock_agent, "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    inputs = iter(["/model", "/model new-model"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=fake_input):
            await run_repl(model="m")

    captured = capsys.readouterr().out
    assert "model: m" in captured
    assert "model: new-model" in captured


@pytest.mark.asyncio
async def test_repl_context_command(capsys: pytest.CaptureFixture) -> None:
    mock_agent = MagicMock()
    mock_agent.session.events = []
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": mock_agent, "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    inputs = iter(["/context"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=fake_input):
            await run_repl(model="m")

    captured = capsys.readouterr().out
    assert "context window" in captured


@pytest.mark.asyncio
async def test_repl_reminders_command(capsys: pytest.CaptureFixture) -> None:
    mock_reminders = MagicMock()
    mock_reminders.report.return_value = "Due:\n  r1"
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": MagicMock(), "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=mock_reminders)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    inputs = iter(["/reminders"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=fake_input):
            await run_repl(model="m")

    captured = capsys.readouterr().out
    assert "Due:" in captured


@pytest.mark.asyncio
async def test_repl_reminders_no_service(
    capsys: pytest.CaptureFixture,
) -> None:
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": MagicMock(), "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    inputs = iter(["/reminders"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=fake_input):
            await run_repl(model="m")

    captured = capsys.readouterr().out
    assert "No reminders service" in captured


@pytest.mark.asyncio
async def test_repl_skill_command(capsys: pytest.CaptureFixture) -> None:
    mock_skills = MagicMock()
    mock_skills.load.return_value = "Skill body"
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": MagicMock(), "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=mock_skills)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    inputs = iter(["/skill test"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=fake_input):
            await run_repl(model="m")

    captured = capsys.readouterr().out
    assert "Skill body" in captured


@pytest.mark.asyncio
async def test_repl_skill_no_service(capsys: pytest.CaptureFixture) -> None:
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": MagicMock(), "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    inputs = iter(["/skill test"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=fake_input):
            await run_repl(model="m")

    captured = capsys.readouterr().out
    assert "No skills service" in captured


@pytest.mark.asyncio
async def test_repl_normal_message(capsys: pytest.CaptureFixture) -> None:
    mock_agent = MagicMock()
    mock_agent.when_idle = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": mock_agent, "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    inputs = iter(["hello"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=fake_input):
            await run_repl(model="m")

    mock_agent.followup.assert_called_once()


@pytest.mark.asyncio
async def test_repl_error_during_turn(capsys: pytest.CaptureFixture) -> None:
    mock_agent = MagicMock()
    mock_agent.when_idle = AsyncMock(side_effect=RuntimeError("boom"))
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": mock_agent, "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    inputs = iter(["hello"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=fake_input):
            await run_repl(model="m")

    captured = capsys.readouterr().out
    assert "Error during turn" in captured


@pytest.mark.asyncio
async def test_repl_empty_input_skipped(
    capsys: pytest.CaptureFixture,
) -> None:
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": MagicMock(), "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    inputs = iter(["", "  "])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=fake_input):
            await run_repl(model="m")


@pytest.mark.asyncio
async def test_repl_keyboard_interrupt(capsys: pytest.CaptureFixture) -> None:
    """KeyboardInterrupt in input is caught and continues the loop."""
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": MagicMock(), "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    call_count = 0

    def input_side_effect(_prompt: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise KeyboardInterrupt
        raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=input_side_effect):
            await run_repl(model="m")

    # Should have printed the interrupt message and continued
    captured = capsys.readouterr().out
    assert "home-swe-home interactive chat" in captured


@pytest.mark.asyncio
async def test_repl_reminder_summary_empty(
    capsys: pytest.CaptureFixture,
) -> None:
    """Empty reminder summary doesn't print."""
    mock_reminders = MagicMock()
    mock_reminders.summary_line.return_value = ""
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": MagicMock(), "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=mock_reminders)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=EOFError):
            await run_repl(model="m")


@pytest.mark.asyncio
async def test_repl_two_messages_sig_already_installed(
    capsys: pytest.CaptureFixture,
) -> None:
    """Second message skips signal handler installation."""
    mock_agent = MagicMock()
    mock_agent.when_idle = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": mock_agent, "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    inputs = iter(["hello", "world"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=fake_input):
            await run_repl(model="m")

    assert mock_agent.followup.call_count == 2


@pytest.mark.asyncio
async def test_repl_reminder_summary_shown(
    capsys: pytest.CaptureFixture,
) -> None:
    mock_reminders = MagicMock()
    mock_reminders.summary_line.return_value = "  1 due"
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": MagicMock(), "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=mock_reminders)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=EOFError):
            await run_repl(model="m")

    captured = capsys.readouterr().out
    assert "1 due" in captured


@pytest.mark.asyncio
async def test_repl_reminder_summary_exception(
    capsys: pytest.CaptureFixture,
) -> None:
    mock_reminders = MagicMock()
    mock_reminders.summary_line.side_effect = RuntimeError("fail")
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(
        return_value={"agent": MagicMock(), "dispose": AsyncMock()}
    )
    mock_ctx.get = MagicMock(return_value=mock_reminders)
    mock_ctx.on = MagicMock(return_value=lambda: None)

    with patch(
        "home_swe_home.repl.build_context", new_callable=AsyncMock
    ) as mock_build:
        mock_build.return_value = mock_ctx
        with patch("builtins.input", side_effect=EOFError):
            await run_repl(model="m")

    # Should not crash — exception is caught


# ---------------------------------------------------------------------------
# _show_context
# ---------------------------------------------------------------------------


def test_show_context(capsys: pytest.CaptureFixture) -> None:
    """Show a message-by-message preview with an estimated token count."""
    mock_agent = MagicMock()
    mock_agent.session.events = []
    mock_agent.session.derive_messages = None

    messages = [
        {"role": "system", "content": [{"type": "text", "text": "SYS"}]},
        {"role": "user", "content": [{"type": "text", "text": "hello there"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]

    with patch("magitech_harness.derive_messages", return_value=messages):
        _show_context(mock_agent)

    captured = capsys.readouterr().out
    assert "context window: 3 messages" in captured
    assert "tokens" in captured
    assert "system" in captured
    assert "hello there" in captured
    assert "assistant" in captured


def test_text_preview_string_content() -> None:
    assert _text_preview("plain text") == "plain text"


def test_text_preview_truncates() -> None:
    long = "x" * 300
    preview = _text_preview(long)
    assert preview.endswith("...")
    assert len(preview) == 203


def test_text_preview_non_text_content() -> None:
    assert _text_preview(12345) == ""
    assert _text_preview([{"type": "image"}]) == ""
