"""Session instructions and token counting.

Builds the system message the model sees on every call. Written once per
session (the first message), never rewritten; new information is appended at
the end so the prompt cache stays valid.
"""

from __future__ import annotations

import datetime
import os
import platform
from typing import Any

import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")

RULES = """\
You are magecode, a coding agent. You work by talking to the user and
calling tools.

Rules:
- Use tools to read, write, edit, search, and run things.
- Every tool call returns a result; read it and act on it.
- If a tool fails, read the error message and try again with different inputs.
- Keep your replies concise and to the point.
- When you are done, tell the user the outcome clearly.
"""


def system_line(*, model: str, cwd: str) -> str:
    """Return a one-line description of where this agent runs."""
    today = datetime.date.today().isoformat()
    return (
        f"System: {platform.system()} {platform.release()}, "
        f"folder: {cwd}, "
        f"date: {today}, "
        f"model: {model}"
    )


def agents_md() -> str:
    """Return the project's AGENTS.md content if it exists."""
    candidates = [
        os.path.join(cwd_for_agents(), "AGENTS.md"),
        "AGENTS.md",
    ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        if content.strip():
            return f"\n--- AGENTS.md ---\n{content}\n--- end AGENTS.md ---\n"
    return ""


def cwd_for_agents() -> str:
    """Return the current working directory (or repo root if run from a child)."""
    return os.getcwd()


def build_system_instructions(*, model: str) -> str:
    """Build the full system message content."""
    parts: list[str] = [RULES]
    parts.append(system_line(model=model, cwd=cwd_for_agents()))
    parts.append(agents_md())
    return "\n".join(parts)


def count_tokens(messages: list[dict[str, Any]]) -> int:
    """Count tokens across all messages using cl100k_base encoding."""
    total = 0
    for message in messages:
        total += len(ENCODING.encode(message.get("role", "") or ""))
        total += len(ENCODING.encode(message.get("content", "") or ""))
        total += 4  # per-message overhead
        tool_calls = message.get("tool_calls")
        if tool_calls:
            for call in tool_calls:
                total += len(ENCODING.encode(call.get("id", "") or ""))
                total += len(ENCODING.encode(call.get("type", "") or ""))
                func = call.get("function", {})
                total += len(ENCODING.encode(func.get("name", "") or ""))
                total += len(ENCODING.encode(func.get("arguments", "") or ""))
                total += 4  # per-tool-call overhead
    return total
