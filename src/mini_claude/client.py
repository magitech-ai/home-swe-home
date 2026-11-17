"""NVIDIA (OpenAI-compatible) API client for mini-claude.

The NVIDIA API key is read from ``NVIDIA_API_KEY`` in the environment. It is
never printed and never persisted by this program.
"""

from __future__ import annotations

import os
from typing import Any

from openai import APIError, OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class MiniClaudeError(Exception):
    """Base error for mini-claude."""


class ConfigurationError(MiniClaudeError):
    """Configuration problem, for example a missing API key."""


def get_api_key() -> str:
    """Return the NVIDIA API key from the environment."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise ConfigurationError(
            "NVIDIA_API_KEY is not set. Get a key at https://build.nvidia.com, "
            "then export it: export NVIDIA_API_KEY=<your key>"
        )
    return api_key


def create_client() -> OpenAI:
    """Build the NVIDIA-compatible OpenAI client.

    Raises ConfigurationError if the API key is missing, so the program fails
    fast with a clear message instead of crashing mid-turn.
    """
    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=get_api_key())


def chat_complete(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> Any:
    """Ask the model for one assistant reply.

    Transport and API errors (bad model, network failure, rate limit) are
    wrapped into MiniClaudeError so callers can report them clearly instead of
    printing a traceback or leaking credentials.
    """
    try:
        # We pass raw message/tool dicts (including tool-result messages)
        # straight to the OpenAI-compatible endpoint, which is looser than
        # openai's strict param types.
        return client.chat.completions.create(  # type: ignore[arg-type]
            model=model,
            messages=messages,  # type: ignore[arg-type]
            tools=tools,  # type: ignore[arg-type]
        )
    except APIError as error:
        raise MiniClaudeError(f"NVIDIA API error: {error}") from error
