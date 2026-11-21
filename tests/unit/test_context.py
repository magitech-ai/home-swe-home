"""Tests for the context module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from home_swe_home.context import (
    DEFAULT_PROVIDER,
    build_context,
    create_agent_async,
    hsh_sessions_dir,
)


def test_hsh_sessions_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_SESSIONS_DIR", raising=False)
    result = hsh_sessions_dir()
    assert "home-swe-home" in str(result)
    assert "sessions" in str(result)


def test_hsh_sessions_dir_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_SESSIONS_DIR", "/tmp/custom-sessions")
    assert hsh_sessions_dir() == Path("/tmp/custom-sessions")


@pytest.mark.asyncio
async def test_build_context_basic(tmp_path: Path) -> None:
    ctx = await build_context(storage_dir=tmp_path)
    defs = ctx.tools.definitions()
    names = {d["name"] for d in defs}
    assert "read_file" in names
    assert "write_file" in names
    assert "run_command" in names


@pytest.mark.asyncio
async def test_build_context_with_providers(tmp_path: Path) -> None:
    ctx = await build_context(storage_dir=tmp_path)
    providers = ctx.llm.list_providers()
    assert any(p["id"] == DEFAULT_PROVIDER for p in providers)


@pytest.mark.asyncio
async def test_build_context_prompt_sections(tmp_path: Path) -> None:
    ctx = await build_context(storage_dir=tmp_path)
    # The system prompt service should have our sections
    assembly = await ctx.system_prompt.assemble({})
    section_names = {s["name"] for s in assembly["sections"]}
    assert "hsh:identity" in section_names
    assert "hsh:system-line" in section_names
    assert "hsh:agents-md" in section_names


@pytest.mark.asyncio
async def test_create_agent_async(tmp_path: Path) -> None:
    ctx = await build_context(storage_dir=tmp_path)

    # Register a mock adapter
    async def _mock_stream(options):
        yield {"type": "finish", "reason": {"kind": "stop"}}

    mock_adapter = MagicMock()
    mock_adapter.provider_info.return_value = {"id": "mock", "name": "Mock"}
    mock_adapter.list_models = AsyncMock(return_value=[])
    mock_adapter.resolve_model = AsyncMock(
        return_value={"provider": "mock", "id": "m1", "name": "M1"}
    )
    mock_adapter.prepare_call = AsyncMock(
        return_value=MagicMock(
            model={"provider": "mock", "id": "m1", "name": "M1"},
            stream=lambda opts: _mock_stream(opts),
        )
    )
    ctx.llm.register_adapter(["mock"], mock_adapter)

    handle = await create_agent_async(ctx, model="m1", session_id="test-sess")
    assert handle["agent"] is not None
    await handle["dispose"]()


@pytest.mark.asyncio
async def test_build_context_default_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_SESSIONS_DIR", "/tmp/test-sessions")
    ctx = await build_context()
    assert ctx is not None


@pytest.mark.asyncio
async def test_skills_catalog_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the skills catalog section returns text when SkillsService is mounted."""
    ctx = await build_context(storage_dir=tmp_path)
    assembly = await ctx.system_prompt.assemble({})
    # The skills catalog section should be present (may be empty if no skills)
    section_names = {s["name"] for s in assembly["sections"]}
    assert "hsh:skills-catalog" in section_names


@pytest.mark.asyncio
async def test_reminders_context(tmp_path: Path) -> None:
    """Verify the reminders runtime context is registered."""
    ctx = await build_context(storage_dir=tmp_path)
    assembly = await ctx.system_prompt.assemble({})
    context_names = {c["name"] for c in assembly["contexts"]}
    assert "hsh:reminders" in context_names
