"""Model API client Service for home-swe-home (OpenAI-compatible endpoints).

NVIDIA is the default provider; set ``HOME_SWE_HOME_PROVIDER=gemini`` and export
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


PROVIDERS = ("gemini", "nvidia")


def config_for(provider: str) -> tuple[str, str, str]:
    """Return (base_url, api_key, label) for an explicit provider.

    Used by the review agent so it can choose a different provider from the
    author without mutating process-wide environment variables.
    """
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ConfigurationError(
                "GEMINI_API_KEY is not set. Export it: export GEMINI_API_KEY=<your key>"
            )
        return GEMINI_BASE_URL, key, "Gemini"
    if provider == "nvidia":
        return NVIDIA_BASE_URL, get_api_key(), "NVIDIA"
    raise ConfigurationError(f"unknown HOME_SWE_HOME_PROVIDER: {provider!r}")


def provider_config() -> tuple[str, str, str]:
    """Return (base_url, api_key, label) for the active provider."""
    return config_for(os.environ.get("HOME_SWE_HOME_PROVIDER", "gemini"))


class MiniClaudeError(Exception):
    """Base error for home-swe-home."""


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


def gemini_api_mode() -> str:
    """Return the Gemini API mode: native Interactions or OpenAI-compatible."""
    mode = os.environ.get("HOME_SWE_HOME_GEMINI_API", "interactions").lower()
    if mode not in {"interactions", "openai"}:
        raise ConfigurationError(
            f"unknown HOME_SWE_HOME_GEMINI_API: {mode!r} (use interactions or openai)"
        )
    return mode


class ClientService(Service):
    """Model adapter: one chat completion request against the active provider.

    Call via ``ctx.client.chat_complete(...)`` or ``chat_stream(...)``. Clients
    are lazy so config errors surface at the call site.
    """

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "client")
        self._openai: OpenAI | None = None
        self._native: Any | None = None
        self._interaction_id: str | None = None

    @property
    def openai(self) -> OpenAI:
        if self._openai is None:
            self._openai = create_client()
        return self._openai

    @property
    def native(self) -> Any:
        if self._native is None:
            from google import genai

            _base, key, _label = provider_config()
            self._native = genai.Client(api_key=key)
        return self._native

    @property
    def use_native(self) -> bool:
        return (
            os.environ.get("HOME_SWE_HOME_PROVIDER", "gemini") == "gemini"
            and gemini_api_mode() == "interactions"
        )

    def _create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        effort: str = "medium",
    ) -> Any:
        """Call the model, wrapping provider API errors consistently."""
        try:
            # Raw dicts (including tool-result messages) are looser than
            # openai's strict param types.
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "tools": tools,
                "stream": stream,
            }
            if os.environ.get("HOME_SWE_HOME_PROVIDER", "gemini") == "gemini":
                kwargs["reasoning_effort"] = effort
            return self.openai.chat.completions.create(  # type: ignore[arg-type]
                **kwargs
            )
        except APIError as error:
            label = (
                "Gemini"
                if os.environ.get("HOME_SWE_HOME_PROVIDER") == "gemini"
                else "NVIDIA"
            )
            raise MiniClaudeError(f"{label} API error: {error}") from error

    def chat_complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        effort: str = "medium",
    ) -> Any:
        """Ask the model for one complete assistant reply."""
        if self.use_native:
            from types import SimpleNamespace

            from .utils.stream import consume_stream

            message = consume_stream(
                self.chat_stream(model=model, messages=messages, tools=tools)
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        return self._create(
            model=model, messages=messages, tools=tools, stream=False, effort=effort
        )

    def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        reasoning: bool = False,
        effort: str = "medium",
    ) -> Any:
        """Open a streamed assistant reply (one delta at a time)."""
        if self.use_native:
            from .native import native_stream

            return native_stream(
                self.native,
                model=model,
                messages=messages,
                tools=tools,
                reasoning=reasoning,
                interaction_id=self._interaction_id,
                on_interaction=self._set_interaction,
                effort=effort,
            )
        return self._create(
            model=model, messages=messages, tools=tools, stream=True, effort=effort
        )

    def _set_interaction(self, interaction_id: str) -> None:
        """Remember the interaction id for stateful follow-up turns."""
        if interaction_id:
            self._interaction_id = interaction_id
