"""Context assembly for home-swe-home on magitech-harness.

Builds an mth Context via ``create_harness``, registers home-swe-home's tools,
LLM adapter, and system prompt sections, and returns the wired context.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from anima import Context
from magitech_harness import create_harness

from .llm.gemini_adapter import GeminiAdapter
from .tools.definitions import register_tools

DEFAULT_MODEL = "gemini-4-hydrogen"
DEFAULT_PROVIDER = "gemini"


def default_model_for(provider: str) -> str:
    """Return the default model id for a provider (env-overridable).

    Kept in sync with the adapters' bound models so selecting a provider
    alone yields a valid model (D-009 fail-closed at resolve_model).
    """
    if provider == "openrouter":
        from .llm.openrouter_adapter import DEFAULT_MODEL as OR_DEFAULT

        return os.environ.get("HOME_SWE_HOME_MODEL", OR_DEFAULT)
    return os.environ.get("HOME_SWE_HOME_MODEL", DEFAULT_MODEL)


def hsh_sessions_dir() -> Path:
    """Return the directory for home-swe-home session logs."""
    override = os.environ.get("HOME_SWE_HOME_SESSIONS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".agents" / "home-swe-home" / "sessions"


async def build_context(
    *,
    storage_dir: Path | None = None,
) -> Context:
    """Create an mth Context with home-swe-home's tools and adapter registered.

    This is the single entry point for assembling a home-swe-home session.
    The CLI and REPL both call this. Must be called from an async context
    (the caller is expected to ``await`` the result).
    """
    if storage_dir is None:
        storage_dir = hsh_sessions_dir()

    ctx = create_harness(storage_dir=storage_dir)

    # Mount home-swe-home app services before flush so they're available.
    # The native SkillsService was retired; Agent Skills are now handled by
    # the mth-components skills system (registry, filesystem, loader) below.
    from .reminders import RemindersService
    from .sandbox import SandboxService

    ctx.use(RemindersService)
    ctx.use(SandboxService)

    # Mount the mth-components OKF + Skills consumption services (3-component
    # pattern: provider registry, filesystem provider, session catalog/loader).
    # These live in mth-plugins and are mounted on the same mth context.
    from mth_plugins.bridges.okf_filesystem.service import OKFFilesystemProviderService
    from mth_plugins.bridges.okf_loader.service import OKFSessionCatalogService
    from mth_plugins.bridges.okf_registry.service import OKFProviderRegistryService
    from mth_plugins.bridges.skills_filesystem.service import (
        SkillsFilesystemProviderService,
    )
    from mth_plugins.bridges.skills_loader.service import SkillsSessionCatalogService
    from mth_plugins.bridges.skills_registry.service import (
        SkillsProviderRegistryService,
    )

    ctx.use(OKFProviderRegistryService)
    ctx.use(OKFFilesystemProviderService)
    ctx.use(OKFSessionCatalogService)
    ctx.use(SkillsProviderRegistryService)
    ctx.use(SkillsFilesystemProviderService)
    ctx.use(SkillsSessionCatalogService)

    # Flush to activate all services (mth bundle + hsh app services + mth-components).
    await ctx.flush()

    # Discover OKF knowledge bundles and Agent Skills, then activate the
    # session catalog + loader tools. The catalogs are injected as
    # <system-reminder> sections and the loaders register okf_bundle({name})
    # and skill({name}) tools for model-driven activation.
    from .utils.home import find_home, trusted_projects

    home = find_home()
    knowledge_dir = (home / "knowledge") if home is not None else None

    ctx.okf_filesystem.discover_bundles(root=knowledge_dir)

    # Agent Skills discovery roots in scope-precedence order (project > home
    # > user). Mirrors the retired native SkillsService._roots() so behavior
    # is unchanged after consolidating onto the mth-components skills system.
    skills_roots: list[tuple[Path, str]] = []
    cwd = Path.cwd()
    if str(cwd) in trusted_projects():
        skills_roots.append((cwd / ".agents" / "skills", "project"))
    if home is not None:
        skills_roots.append((home / "skills", "home"))
    skills_roots.append((Path.home() / ".agents" / "skills", "user"))
    ctx.skills_filesystem.discover_skills(roots=skills_roots)

    ctx.okf_loader.activate()
    ctx.skills_loader.activate()

    # Register LLM adapters (requires ctx.llm to be active). Both are always
    # available; the active provider is selected by HOME_SWE_HOME_PROVIDER
    # (or the CLI/programmatic agent options). OpenRouter is bound to
    # tencent/hy4-flash with high reasoning effort.
    from .llm.openrouter_adapter import OpenRouterAdapter

    ctx.llm.register_adapter(["gemini"], GeminiAdapter())
    ctx.llm.register_adapter(["openrouter"], OpenRouterAdapter())

    # Register all home-swe-home tools (requires ctx.tools to be active).
    register_tools(ctx)

    # Register system prompt sections (requires ctx.system_prompt to be active).
    _register_prompt_sections(ctx)

    return ctx


def _register_prompt_sections(ctx: Context) -> None:
    """Register home-swe-home's system prompt sections on ctx.system_prompt."""
    from .instructions import agents_md, base_instructions, system_line

    # Identity section — read from the editable harness tree so the prompt
    # stays data, not code (HOME_SWE_HOME_HARNESS_DIR can point elsewhere).
    ctx.system_prompt.section(
        {
            "name": "hsh:identity",
            "order": -500,
            "text": lambda _ctx: base_instructions(),
        }
    )

    # System line (OS, cwd, date, model)
    ctx.system_prompt.section(
        {
            "name": "hsh:system-line",
            "order": 100,
            "text": lambda _ctx: system_line(),
        }
    )

    # AGENTS.md from home and current repo
    ctx.system_prompt.section(
        {
            "name": "hsh:agents-md",
            "order": 200,
            "text": lambda _ctx: agents_md(),
        }
    )

    # Note: the skills catalog is injected by the mth-components skills-loader
    # (SkillsSessionCatalogService) as a <system-reminder> section, so hsh does
    # not register a duplicate hsh:skills-catalog section here.

    # Reminders — dynamic, reads from the mounted RemindersService.
    def _reminders_block(_ctx: Any) -> str:
        reminders = ctx.get("reminders", None, strict=False)
        if reminders is not None:
            return str(reminders.due_block())
        return ""  # pragma: no cover — services are always mounted in build_context

    ctx.system_prompt.context(
        {
            "name": "hsh:reminders",
            "order": 110,
            "required": True,
            "text": _reminders_block,
        }
    )


async def create_agent_async(
    ctx: Context,
    *,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    session_id: str | None = None,
) -> Any:
    """Create an agent on the context and return the handle.

    Provider/model/effort default to the env-adjusted defaults so the
    OpenRouter + Hy4 combination can be selected with
    ``HOME_SWE_HOME_PROVIDER=openrouter``.
    """
    active_provider = provider or os.environ.get(
        "HOME_SWE_HOME_PROVIDER", DEFAULT_PROVIDER
    )
    active_model = model or default_model_for(active_provider)
    options: dict[str, Any] = {
        "provider": active_provider,
        "model": active_model,
    }
    if reasoning_effort:
        options["reasoningEffort"] = reasoning_effort
    handle = await ctx.agents.create(
        {
            "sessionId": session_id or f"hsh-{uuid.uuid4()}",
            "agentOptions": options,
        }
    )
    return handle
