"""Session instructions and token counting as an anima Service component.

Builds the system message the model sees on every call. Written once per
session (the first message), never rewritten; new information is appended at
the end so the prompt cache stays valid.

Access via ``ctx.instructions.build(...)`` and ``ctx.instructions.count(...)``.
"""

from __future__ import annotations

import datetime
import os
import platform
from typing import Any

import tiktoken
from anima import Context, Service

from .utils.harness import system_prompt

ENCODING = tiktoken.get_encoding("cl100k_base")


class InstructionsService(Service):
    """System prompt assembly and token counting for the session."""

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "instructions")

    def system_line(self, *, model: str, cwd: str) -> str:
        """Return a one-line description of where this agent runs."""
        today = datetime.date.today().isoformat()
        return (
            f"System: {platform.system()} {platform.release()}, "
            f"folder: {cwd}, "
            f"date: {today}, "
            f"model: {model}"
        )

    def agents_md(self) -> str:
        """Return the project's AGENTS.md content if it exists."""
        for path in (os.path.join(os.getcwd(), "AGENTS.md"), "AGENTS.md"):
            try:
                with open(path, encoding="utf-8") as handle:
                    content = handle.read()
            except (OSError, UnicodeDecodeError):
                continue
            if content.strip():
                return f"\n--- AGENTS.md ---\n{content}\n--- end AGENTS.md ---\n"
        return ""

    def build(self, *, model: str) -> str:
        """Build the full system message content."""
        return "\n".join(
            [
                system_prompt(),
                self.system_line(model=model, cwd=os.getcwd()),
                self.agents_md(),
            ]
        )

    def count(self, messages: list[dict[str, Any]]) -> int:
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
