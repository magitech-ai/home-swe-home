"""NVIDIA (OpenAI-compatible) API client Service for magecode.

The NVIDIA API key is read from ``NVIDIA_API_KEY`` in the environment. It is
never printed and never persisted by this program.

As anima Service component: ``ctx.client.chat_complete(...)``. Config errors
and API errors are wrapped into types callers can report clearly.
"""

from __future__ import annotations

import os
from typing import Any

from anima import Context, Service
from openai import APIError, OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class MiniClaudeError(Exception):
    """Base error for magecode."""


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
    """Build the NVIDIA-compatible OpenAI client, failing fast on no key."""
    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=get_api_key())


class ClientService(Service):
    """Model adapter: one chat completion request against NVIDIA's endpoint.

    Call via ``ctx.client.chat_complete(...)``. The OpenAI client is created
    lazily on first use so config errors surface at the call site.
    """

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "client")
        self._openai: OpenAI | None = None

    @property
    def openai(self) -> OpenAI:
        if self._openai is None:
            self._openai = create_client()
        return self._openai

    def chat_complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> Any:
        """Ask the model for one assistant reply, wrapping API errors."""
        try:
            # Raw dicts (including tool-result messages) are looser than
            # openai's strict param types.
            return self.openai.chat.completions.create(  # type: ignore[arg-type]
                model=model,
                messages=messages,  # type: ignore[arg-type]
                tools=tools,  # type: ignore[arg-type]
            )
        except APIError as error:
            raise MiniClaudeError(f"NVIDIA API error: {error}") from error
