"""Tests for magecode.client (ClientService + config helpers)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx2
import pytest
from anima import Context
from openai import APIConnectionError, APIStatusError

from magecode.client import (
    NVIDIA_BASE_URL,
    ClientService,
    ConfigurationError,
    MiniClaudeError,
    create_client,
    get_api_key,
    provider_config,
)


def _service_with(openai_client) -> ClientService:
    ctx = Context()
    ctx.use(ClientService)
    service = ctx.client  # type: ignore[assignment]
    service._openai = openai_client  # inject fake; avoids env/network
    return service


def test_client_service_lazy_creation(monkeypatch):
    """ClientService creates the OpenAI client on first use."""
    from anima import Context

    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    ctx = Context()
    ctx.use(ClientService)
    service = ctx.client  # type: ignore[assignment]
    assert service._openai is None
    openai = service.openai  # triggers lazy creation
    assert openai is not None
    assert service.openai is openai  # cached


def test_get_api_key_returns_env_value(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    assert get_api_key() == "nvapi-test-key"


def test_get_api_key_missing(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="NVIDIA_API_KEY is not set"):
        get_api_key()


def test_create_client_missing_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        create_client()


def test_create_client_passes_key_and_base_url(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    with patch_openai() as mock_openai:
        create_client()
    mock_openai.assert_called_once_with(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="nvapi-test-key",
    )


def test_chat_complete_returns_response():
    response = SimpleNamespace(choices=[])
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: response)
        )
    )
    service = _service_with(client)
    assert service.chat_complete(model="m", messages=[], tools=None) is response


def test_chat_complete_wraps_status_error():
    response = httpx2.Response(
        404, request=httpx2.Request("POST", "https://x/v1/chat/completions")
    )
    error = APIStatusError("The model does not exist", response=response, body=None)
    service = _service_with(failing_client(error))
    expected = "NVIDIA API error: The model does not exist"
    with pytest.raises(MiniClaudeError, match=expected):
        service.chat_complete(model="nope/nope", messages=[], tools=None)


def test_chat_complete_wraps_connection_error():
    error = APIConnectionError(
        message="failed to connect",
        request=httpx2.Request("POST", "https://x"),
    )
    service = _service_with(failing_client(error))
    with pytest.raises(MiniClaudeError, match="NVIDIA API error: failed to connect"):
        service.chat_complete(model="m", messages=[], tools=None)


def patch_openai():
    from unittest.mock import patch

    return patch("magecode.client.OpenAI")


def failing_client(error):
    def create(**kwargs):
        raise error

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def test_provider_config_nvidia(monkeypatch):
    monkeypatch.delenv("MAGECODE_PROVIDER", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    assert provider_config()[2] == "NVIDIA"
    assert provider_config()[0] == NVIDIA_BASE_URL


def test_provider_config_gemini(monkeypatch):
    monkeypatch.setenv("MAGECODE_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    base, key, label = provider_config()
    assert label == "Gemini" and key == "gemini-test"
    assert "generativelanguage" in base


def test_provider_config_gemini_google_key(monkeypatch):
    monkeypatch.setenv("MAGECODE_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test")
    assert provider_config()[1] == "google-test"


def test_provider_config_gemini_missing_key(monkeypatch):
    monkeypatch.setenv("MAGECODE_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        provider_config()


def test_provider_config_unknown(monkeypatch):
    monkeypatch.setenv("MAGECODE_PROVIDER", "bogus")
    with pytest.raises(ConfigurationError, match="unknown MAGECODE_PROVIDER"):
        provider_config()


def test_chat_stream_passes_stream_flag():
    service = _service_with(
        SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: kwargs)
            )
        )
    )
    result = service.chat_stream(model="m", messages=[], tools=None)
    assert result["stream"] is True


def test_chat_complete_passes_stream_false():
    service = _service_with(
        SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: kwargs)
            )
        )
    )
    assert service.chat_complete(model="m", messages=[], tools=None)["stream"] is False


def test_gemini_api_mode(monkeypatch):
    from magecode.client import gemini_api_mode

    monkeypatch.setenv("MAGECODE_PROVIDER", "gemini")
    monkeypatch.delenv("MAGECODE_GEMINI_API", raising=False)
    assert gemini_api_mode() == "interactions"
    monkeypatch.setenv("MAGECODE_GEMINI_API", "openai")
    assert gemini_api_mode() == "openai"
    monkeypatch.setenv("MAGECODE_GEMINI_API", "bad")
    with pytest.raises(ConfigurationError, match="unknown MAGECODE_GEMINI_API"):
        gemini_api_mode()


def test_use_native_selection(monkeypatch):
    from magecode.client import ClientService

    ctx = Context()
    ctx.use(ClientService)
    service = ctx.client
    monkeypatch.setenv("MAGECODE_PROVIDER", "gemini")
    monkeypatch.delenv("MAGECODE_GEMINI_API", raising=False)
    assert service.use_native is True
    monkeypatch.setenv("MAGECODE_GEMINI_API", "openai")
    assert service.use_native is False
    monkeypatch.setenv("MAGECODE_PROVIDER", "nvidia")
    assert service.use_native is False


def test_chat_stream_native_mode(monkeypatch):
    from magecode.client import ClientService

    ctx = Context()
    ctx.use(ClientService)
    service = ctx.client
    monkeypatch.setenv("MAGECODE_PROVIDER", "gemini")
    monkeypatch.delenv("MAGECODE_GEMINI_API", raising=False)
    service._native = object()
    seen = {}

    def fake_native_stream(client, **kwargs):
        seen.update(kwargs)
        return ["chunk"]

    monkeypatch.setattr("magecode.native.native_stream", fake_native_stream)
    assert service.chat_stream(model="m", messages=[], tools=None, reasoning=True) == [
        "chunk"
    ]
    assert seen["reasoning"] is True
    seen["on_interaction"]("i1")
    assert service._interaction_id == "i1"
    seen["on_interaction"]("")
    assert service._interaction_id == "i1"


def test_chat_complete_native_mode(monkeypatch):
    from magecode.client import ClientService

    ctx = Context()
    ctx.use(ClientService)
    service = ctx.client
    monkeypatch.setenv("MAGECODE_PROVIDER", "gemini")
    monkeypatch.delenv("MAGECODE_GEMINI_API", raising=False)
    service._native = object()
    monkeypatch.setattr(service, "chat_stream", lambda **kwargs: [])
    result = service.chat_complete(model="m", messages=[], tools=None)
    assert result.choices[0].message.content == ""


def test_native_client_is_lazy(monkeypatch):
    from magecode.client import ClientService

    ctx = Context()
    ctx.use(ClientService)
    service = ctx.client
    monkeypatch.setenv("MAGECODE_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.delenv("MAGECODE_GEMINI_API", raising=False)
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: "fake-client")
    assert service.native == "fake-client"
    assert service.native == "fake-client"
