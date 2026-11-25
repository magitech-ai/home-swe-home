"""Tests for the context module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from home_swe_home.context import (
    DEFAULT_PROVIDER,
    build_context,
    create_agent_async,
    default_model_for,
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
    assert "bash" in names
    assert "grep" in names


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

    handle = await create_agent_async(
        ctx,
        model="m1",
        provider="mock",
        reasoning_effort="high",
        session_id="test-sess",
    )
    assert handle["agent"] is not None
    await handle["dispose"]()


@pytest.mark.asyncio
async def test_build_context_all_skills_scopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Project (trusted cwd) and home skill scopes are added to discovery."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("home_swe_home.utils.home.find_home", lambda: home)
    monkeypatch.setattr(
        "home_swe_home.utils.home.trusted_projects", lambda: (str(Path.cwd()),)
    )
    ctx = await build_context(storage_dir=tmp_path / "sessions")
    assert ctx is not None


@pytest.mark.asyncio
async def test_build_context_no_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No home checkout still builds a context (home scope skipped)."""
    monkeypatch.setattr("home_swe_home.utils.home.find_home", lambda: None)
    monkeypatch.setattr("home_swe_home.utils.home.trusted_projects", lambda: ())
    ctx = await build_context(storage_dir=tmp_path)
    assert ctx is not None


@pytest.mark.asyncio
async def test_create_agent_async_env_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider/model come from env when not passed explicitly."""
    monkeypatch.setenv("HOME_SWE_HOME_PROVIDER", "openrouter")
    monkeypatch.setenv("HOME_SWE_HOME_MODEL", "tencent/hy4-flash")
    ctx = await build_context(storage_dir=tmp_path)
    captured: dict = {}

    async def _create(payload):
        captured["opts"] = payload["agentOptions"]
        agent = MagicMock()
        return {"agent": agent, "dispose": AsyncMock()}

    ctx.agents.create = AsyncMock(side_effect=_create)
    handle = await create_agent_async(ctx, session_id="env-sess")
    assert captured["opts"]["provider"] == "openrouter"
    assert captured["opts"]["model"] == "tencent/hy4-flash"
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
    """The mth-components skills-loader injects the model-facing skills catalog.

    Register a skill explicitly so the assertion does not depend on a local
    agents-home checkout being present (CI has none).
    """
    from mth_components.bridges.skills_registry.service import (
        SkillBundleInfo,
        SkillsProviderRegistryService,
    )

    ctx = await build_context(storage_dir=tmp_path)
    registry: SkillsProviderRegistryService = ctx.skills_registry
    registry.register_skill(
        SkillBundleInfo(
            name="test-skill",
            description="A test skill",
            path=tmp_path,
            skill_file=tmp_path / "SKILL.md",
            body="body",
        )
    )
    ctx.skills_loader.activate()
    assembly = await ctx.system_prompt.assemble({})
    section_names = {s["name"] for s in assembly["sections"]}
    assert "skills_catalog" in section_names
    assert ctx.tools.get("skill") is not None
    assert ctx.tools.get("okf_bundle") is not None


@pytest.mark.asyncio
async def test_reminders_context(tmp_path: Path) -> None:
    """Verify the reminders runtime context is registered."""
    ctx = await build_context(storage_dir=tmp_path)
    assembly = await ctx.system_prompt.assemble({})
    context_names = {c["name"] for c in assembly["contexts"]}
    assert "hsh:reminders" in context_names


def test_default_model_for_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """default_model_for selects a valid model per provider (no env override)."""
    monkeypatch.delenv("HOME_SWE_HOME_MODEL", raising=False)
    assert default_model_for("gemini") == "gemini-4-hydrogen"
    assert default_model_for("openrouter") == "tencent/hy4-flash"
    monkeypatch.setenv("HOME_SWE_HOME_MODEL", "custom/model")
    assert default_model_for("gemini") == "custom/model"
    assert default_model_for("openrouter") == "custom/model"


@pytest.mark.asyncio
async def test_build_context_discovers_okf_from_multiple_scopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OKF discovery uses project/home/user scope precedence like skills."""
    from mth_components.bridges.okf_filesystem.service import (
        OKFFilesystemProviderService,
    )

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr("home_swe_home.utils.home.find_home", lambda: fake_home)
    monkeypatch.setattr(
        "home_swe_home.utils.home.trusted_projects", lambda: (str(Path.cwd()),)
    )
    seen: list[list[tuple[Path, str]]] = []
    original = OKFFilesystemProviderService.discover_bundles

    def _spy(self: object, roots: list[tuple[Path, str]] | None = None) -> list[str]:
        seen.append(roots or [])
        return original(self, roots)

    monkeypatch.setattr(OKFFilesystemProviderService, "discover_bundles", _spy)
    await build_context(storage_dir=tmp_path)
    assert seen, "OKF discovery was not called"
    roots = seen[0]
    assert [scope for _root, scope in roots] == ["project", "home", "user"]
    assert roots[0][0] == Path.cwd() / ".agents" / "knowledge"
    assert roots[1][0] == fake_home / "knowledge"
    assert roots[2][0] == Path.home() / ".agents" / "knowledge"
