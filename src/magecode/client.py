"""Model API client Service for magecode (OpenAI-compatible endpoints).

NVIDIA is the default provider; set ``MAGECODE_PROVIDER=gemini`` and export
``GEMINI_API_KEY`` to use Gemini's OpenAI-compatible endpoint instead. Keys are
never printed or persisted by this program.

As anima Service component: ``ctx.client.chat_complete(...)``. Config errors
and API errors are wrapped into types callers can report clearly.
"""

from __future__ import annotations

import os
from typing import Any

from anima import Context, Service
from openai import APIError, OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def provider_config() -> tuple[str, str, str]:
    """Return (base_url, api_key, label) for the active provider."""
    provider = os.environ.get("MAGECODE_PROVIDER", "nvidia")
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ConfigurationError(
                "GEMINI_API_KEY is not set. Export it: export GEMINI_API_KEY=<your key>"
            )
        return GEMINI_BASE_URL, key, "Gemini"
    if provider != "nvidia":
        raise ConfigurationError(f"unknown MAGECODE_PROVIDER: {provider!r}")
    return NVIDIA_BASE_URL, get_api_key(), "NVIDIA"


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
    """Build the OpenAI-compatible client, failing fast on no key."""
    base_url, key, _label = provider_config()
    return OpenAI(base_url=base_url, api_key=key)


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

    def _create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        stream: bool,
    ) -> Any:
        """Call the model, wrapping provider API errors consistently."""
        try:
            # Raw dicts (including tool-result messages) are looser than
            # openai's strict param types.
            return self.openai.chat.completions.create(  # type: ignore[arg-type]
                model=model,
                messages=messages,  # type: ignore[arg-type]
                tools=tools,  # type: ignore[arg-type]
                stream=stream,
            )
        except APIError as error:
            label = (
                "Gemini"
                if os.environ.get("MAGECODE_PROVIDER") == "gemini"
                else "NVIDIA"
            )
            raise MiniClaudeError(f"{label} API error: {error}") from error

    def chat_complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> Any:
        """Ask the model for one complete assistant reply."""
        return self._create(model=model, messages=messages, tools=tools, stream=False)

    def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> Any:
        """Open a streamed assistant reply (one delta at a time)."""
        return self._create(model=model, messages=messages, tools=tools, stream=True)
