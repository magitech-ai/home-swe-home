"""System prompt helpers for home-swe-home on magitech-harness.

These functions build the text content for system prompt sections registered
on ``ctx.system_prompt``. They are pure functions — no Service, no state.
"""

from __future__ import annotations

import datetime
import os
import platform
from pathlib import Path


def system_line(*, model: str = "", cwd: str = "") -> str:
    """Return a one-line description of where this agent runs."""
    today = datetime.date.today().isoformat()
    return (
        f"System: {platform.system()} {platform.release()}, "
        f"folder: {cwd or os.getcwd()}, "
        f"date: {today}, "
        f"model: {model or 'unknown'}"
    )


def agents_md() -> str:
    """Return home guidance first, then the current repo's AGENTS.md.

    Home guidance is always included; the current repo's file is appended
    when it differs. Paths are deduplicated by resolved location so running
    from the home checkout does not duplicate its guidance.
    """
    from .utils.home import find_home

    home = find_home()
    paths = [home / "AGENTS.md"] if home is not None else []
    paths.append(Path(os.getcwd()) / "AGENTS.md")

    parts: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            content = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if content.strip():
            parts.append(f"\n--- AGENTS.md ---\n{content}\n--- end AGENTS.md ---\n")
    return "".join(parts)