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
    from .reminders import RemindersService
    from .sandbox import SandboxService
    from .skills import SkillsService

    ctx.use(SkillsService)
    ctx.use(RemindersService)
    ctx.use(SandboxService)

    # Flush to activate all services (mth bundle + hsh app services).
    await ctx.flush()

    # Register the Gemini LLM adapter (requires ctx.llm to be active).
    ctx.llm.register_adapter([DEFAULT_PROVIDER], GeminiAdapter())

    # Register all home-swe-home tools (requires ctx.tools to be active).
    register_tools(ctx)

    # Register system prompt sections (requires ctx.system_prompt to be active).
    _register_prompt_sections(ctx)

    return ctx


def _register_prompt_sections(ctx: Context) -> None:
    """Register home-swe-home's system prompt sections on ctx.system_prompt."""
    from .instructions import agents_md, system_line

    # Identity section
    ctx.system_prompt.section(
        {
            "name": "hsh:identity",
            "order": -500,
            "text": "You are home-swe-home, a coding agent. You help with software "
            "engineering tasks: reading and editing code, running commands, "
            "searching the web, and verifying that changes pass checks.",
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

    # Skills catalog — dynamic, reads from the mounted SkillsService.
    def _skills_catalog(_ctx: Any) -> str:
        skills = ctx.get("skills", None, strict=False)
        if skills is not None:
            return str(skills.catalog())
        return ""

    ctx.system_prompt.section(
        {
            "name": "hsh:skills-catalog",
            "order": 300,
            "text": _skills_catalog,
        }
    )

    # Reminders — dynamic, reads from the mounted RemindersService.
    def _reminders_block(_ctx: Any) -> str:
        reminders = ctx.get("reminders", None, strict=False)
        if reminders is not None:
            return str(reminders.due_block())
        return ""

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
    model: str = DEFAULT_MODEL,
    session_id: str | None = None,
) -> Any:
    """Create an agent on the context and return the handle."""
    handle = await ctx.agents.create(
        {
            "sessionId": session_id or f"hsh-{uuid.uuid4()}",
            "agentOptions": {
                "provider": DEFAULT_PROVIDER,
                "model": model,
            },
        }
    )
    return handle
