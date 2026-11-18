"""Redact known secret values from tool output.

A model can ask a tool to read a local ``.env`` or print an environment
variable. Redaction at the tool-result boundary prevents that value from ever
reaching the conversation, regardless of which tool produced it.
"""

from __future__ import annotations

import os

SECRET_ENV_NAMES = (
    "NVIDIA_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
)


def secret_values() -> tuple[str, ...]:
    """Return currently set secret values from the environment."""
    return tuple(value for name in SECRET_ENV_NAMES if (value := os.environ.get(name)))


def redact(text: str) -> str:
    """Replace every known secret value in *text* with ``<redacted>``."""
    for value in secret_values():
        text = text.replace(value, "<redacted>")
    return text
