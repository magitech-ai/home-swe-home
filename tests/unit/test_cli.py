"""Tests for the CLI module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from home_swe_home.cli import (
    _run_async,
    _run_headless,
    build_parser,
    main,
)

# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


def test_build_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.sandbox is True
    assert args.model is not None


def test_build_parser_no_sandbox() -> None:
    parser = build_parser()
    args = parser.parse_args(["--no-sandbox"])
    assert args.sandbox is False


def test_build_parser_prompt() -> None:
    parser = build_parser()
    args = parser.parse_args(["-p", "hello"])
    assert args.prompt == "hello"


def test_build_parser_model() -> None:
    parser = build_parser()
    args = parser.parse_args(["--model", "test-model"])
    assert args.model == "test-model"


def test_build_parser_effort() -> None:
    parser = build_parser()
    args = parser.parse_args(["--effort", "high"])
    assert args.effort == "high"


def test_build_parser_init_home() -> None:
    parser = build_parser()
    args = parser.parse_args(["--init-home", "/tmp/home", "--home-repo", "org/repo"])
    assert args.init_home == "/tmp/home"
    assert args.home_repo == "org/repo"


# ---------------------------------------------------------------------------
# _run_async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_async_no_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    rc = await _run_async(["-p", "hello"])
    assert rc == 2


@pytest.mark.asyncio
async def test_run_async_init_home_no_repo() -> None:
    rc = await _run_async(["--init-home", "/tmp/home"])
    assert rc == 2


@pytest.mark.asyncio
async def test_run_async_init_home_plan(capsys: pytest.CaptureFixture) -> None:
    with patch("home_swe_home.onboard.plan_wizard") as mock_plan:
        mock_plan.return_value = {"path": "/tmp/home", "repo": "org/repo"}
        rc = await _run_async(
            ["--init-home", "/tmp/home", "--home-repo", "org/repo", "--plan"]
        )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "path" in captured


@pytest.mark.asyncio
async def test_run_async_init_home_plan_json(
    capsys: pytest.CaptureFixture,
) -> None:
    with patch("home_swe_home.onboard.plan_wizard") as mock_plan:
        mock_plan.return_value = {"path": "/tmp/home"}
        rc = await _run_async(
            [
                "--init-home",
                "/tmp/home",
                "--home-repo",
                "org/repo",
                "--plan",
                "--json",
            ]
        )
    assert rc == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["path"] == "/tmp/home"


@pytest.mark.asyncio
async def test_run_async_init_home_already_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("home_swe_home.cli.find_home", lambda: Path("/existing"))
    rc = await _run_async(["--init-home", "/tmp/home", "--home-repo", "org/repo"])
    assert rc == 2


@pytest.mark.asyncio
async def test_run_async_init_home_force(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr("home_swe_home.cli.find_home", lambda: Path("/existing"))
    with patch("home_swe_home.cli.run_wizard", return_value=True):
        rc = await _run_async(
            [
                "--init-home",
                "/tmp/home",
                "--home-repo",
                "org/repo",
                "--force",
                "--yes",
            ]
        )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "Home scaffolded" in captured


@pytest.mark.asyncio
async def test_run_async_init_home_interactive(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr("home_swe_home.cli.find_home", lambda: None)
    with patch("home_swe_home.cli.run_wizard", return_value=True):
        with patch("builtins.input", return_value="y"):
            rc = await _run_async(
                [
                    "--init-home",
                    "/tmp/home",
                    "--home-repo",
                    "org/repo",
                ]
            )
    assert rc == 0


@pytest.mark.asyncio
async def test_run_async_init_home_json_accepted(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr("home_swe_home.cli.find_home", lambda: None)
    with patch("home_swe_home.cli.run_wizard", return_value=True):
        rc = await _run_async(
            [
                "--init-home",
                "/tmp/home",
                "--home-repo",
                "org/repo",
                "--yes",
                "--json",
            ]
        )
    assert rc == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["accepted"] is True


@pytest.mark.asyncio
async def test_run_async_init_home_declined(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr("home_swe_home.cli.find_home", lambda: None)
    with patch("home_swe_home.cli.run_wizard", return_value=False):
        rc = await _run_async(
            [
                "--init-home",
                "/tmp/home",
                "--home-repo",
                "org/repo",
                "--yes",
            ]
        )
    assert rc == 1


@pytest.mark.asyncio
async def test_run_async_no_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    with patch("home_swe_home.cli._run_headless", new_callable=AsyncMock) as mock_h:
        mock_h.return_value = 0
        rc = await _run_async(["-p", "hello", "--no-sandbox"])

    assert rc == 0
    from home_swe_home.sandbox import sandbox_enabled

    assert sandbox_enabled() is False


@pytest.mark.asyncio
async def test_run_async_headless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    with patch("home_swe_home.cli._run_headless", new_callable=AsyncMock) as mock_h:
        mock_h.return_value = 0
        rc = await _run_async(["-p", "hello"])

    assert rc == 0
    mock_h.assert_called_once()


@pytest.mark.asyncio
async def test_run_async_repl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    with patch("home_swe_home.repl.run_repl", new_callable=AsyncMock) as mock_repl:
        rc = await _run_async([])

    assert rc == 0
    mock_repl.assert_called_once()


# ---------------------------------------------------------------------------
# _run_headless
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_headless_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_agent = MagicMock()
    mock_agent.session.events = []
    mock_agent.when_idle = AsyncMock()
    mock_agent.followup = MagicMock()
    mock_handle = {"agent": mock_agent, "dispose": AsyncMock()}
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(return_value=mock_handle)

    mock_outcome = MagicMock()
    mock_outcome.text = "Hello"
    mock_outcome.reason = {"kind": "completed"}

    with patch("home_swe_home.cli.build_context", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = mock_ctx
        with patch(
            "magitech_harness.cli.summarize_headless_outcome",
            return_value=mock_outcome,
        ):
            rc = await _run_headless(model="m", prompt="hello")

    assert rc == 0


@pytest.mark.asyncio
async def test_run_headless_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_agent = MagicMock()
    mock_agent.session.events = []
    mock_agent.when_idle = AsyncMock()
    mock_agent.followup = MagicMock()
    mock_handle = {"agent": mock_agent, "dispose": AsyncMock()}
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(return_value=mock_handle)

    mock_outcome = MagicMock()
    mock_outcome.text = ""
    mock_outcome.reason = {
        "kind": "error",
        "error": {"code": "RATE_LIMIT", "message": "Too many requests"},
    }

    with patch("home_swe_home.cli.build_context", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = mock_ctx
        with patch(
            "magitech_harness.cli.summarize_headless_outcome",
            return_value=mock_outcome,
        ):
            rc = await _run_headless(model="m", prompt="hello")

    assert rc == 1


@pytest.mark.asyncio
async def test_run_headless_error_no_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_agent = MagicMock()
    mock_agent.session.events = []
    mock_agent.when_idle = AsyncMock()
    mock_agent.followup = MagicMock()
    mock_handle = {"agent": mock_agent, "dispose": AsyncMock()}
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(return_value=mock_handle)

    mock_outcome = MagicMock()
    mock_outcome.text = ""
    mock_outcome.reason = {"kind": "error", "error": "string error"}

    with patch("home_swe_home.cli.build_context", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = mock_ctx
        with patch(
            "magitech_harness.cli.summarize_headless_outcome",
            return_value=mock_outcome,
        ):
            rc = await _run_headless(model="m", prompt="hello")

    assert rc == 1


@pytest.mark.asyncio
async def test_run_headless_other_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_agent = MagicMock()
    mock_agent.session.events = []
    mock_agent.when_idle = AsyncMock()
    mock_agent.followup = MagicMock()
    mock_handle = {"agent": mock_agent, "dispose": AsyncMock()}
    mock_ctx = MagicMock()
    mock_ctx.agents.create = AsyncMock(return_value=mock_handle)

    mock_outcome = MagicMock()
    mock_outcome.text = "partial"
    mock_outcome.reason = {"kind": "blocked"}

    with patch("home_swe_home.cli.build_context", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = mock_ctx
        with patch(
            "magitech_harness.cli.summarize_headless_outcome",
            return_value=mock_outcome,
        ):
            rc = await _run_headless(model="m", prompt="hello")

    assert rc == 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_returns_asyncio_run() -> None:
    def fake_run(coro):
        coro.close()
        return 42

    with patch("asyncio.run", side_effect=fake_run) as mock_run:
        result = main([])
    assert result == 42
    mock_run.assert_called_once()
