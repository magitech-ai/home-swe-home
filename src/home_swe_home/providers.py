"""Provider configuration helpers for the review/audit tools.

These tools use the OpenAI client directly (not the mth agent loop) because
they are independent reviewers that run outside the main agent session.
"""

from __future__ import annotations

import os

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

PROVIDERS = ("gemini", "nvidia", "openrouter")


class AgentHomeError(Exception):
    """Base error for home-swe-home."""


class ConfigurationError(AgentHomeError):
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


def config_for(provider: str) -> tuple[str, str, str]:
    """Return (base_url, api_key, label) for an explicit provider."""
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ConfigurationError(
                "GEMINI_API_KEY is not set. Export it: export GEMINI_API_KEY=<your key>"
            )
        return GEMINI_BASE_URL, key, "Gemini"
    if provider == "nvidia":
        return NVIDIA_BASE_URL, get_api_key(), "NVIDIA"
    if provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ConfigurationError(
                "OPENROUTER_API_KEY is not set. Create a key at "
                "https://openrouter.ai/keys, then export it: "
                "export OPENROUTER_API_KEY=<your key>"
            )
        return OPENROUTER_BASE_URL, key, "OpenRouter"
    raise ConfigurationError(f"unknown HOME_SWE_HOME_PROVIDER: {provider!r}")
