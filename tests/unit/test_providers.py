"""Tests for the providers module."""

from __future__ import annotations

import pytest

from home_swe_home.providers import (
    GEMINI_BASE_URL,
    NVIDIA_BASE_URL,
    OPENROUTER_BASE_URL,
    PROVIDERS,
    AgentHomeError,
    ConfigurationError,
    config_for,
    get_api_key,
)


def test_agent_home_error_is_exception() -> None:
    assert issubclass(AgentHomeError, Exception)


def test_configuration_error_is_agent_home_error() -> None:
    assert issubclass(ConfigurationError, AgentHomeError)


def test_get_api_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-key")
    assert get_api_key() == "nvidia-key"


def test_get_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="NVIDIA_API_KEY is not set"):
        get_api_key()


def test_config_for_gemini_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    base_url, key, label = config_for("gemini")
    assert base_url == GEMINI_BASE_URL
    assert key == "gemini-key"
    assert label == "Gemini"


def test_config_for_gemini_google_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    _base_url, key, _label = config_for("gemini")
    assert key == "google-key"


def test_config_for_gemini_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is not set"):
        config_for("gemini")


def test_config_for_nvidia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-key")
    base_url, key, label = config_for("nvidia")
    assert base_url == NVIDIA_BASE_URL
    assert key == "nv-key"
    assert label == "NVIDIA"


def test_config_for_nvidia_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="NVIDIA_API_KEY is not set"):
        config_for("nvidia")


def test_config_for_unknown() -> None:
    with pytest.raises(ConfigurationError, match="unknown HOME_SWE_HOME_PROVIDER"):
        config_for("unknown")


# ---------------------------------------------------------------------------
# OpenRouter
# ---------------------------------------------------------------------------


def test_openrouter_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    base_url, key, label = config_for("openrouter")
    assert base_url == OPENROUTER_BASE_URL
    assert key == "or-key"
    assert label == "OpenRouter"


def test_openrouter_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY is not set"):
        config_for("openrouter")


def test_openrouter_is_a_known_provider() -> None:
    assert "openrouter" in PROVIDERS
