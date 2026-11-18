"""Tests for magecode.client (ClientService + config helpers)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from anima import Context
from openai import APIConnectionError, APIStatusError

from magecode.client import (
    ClientService,
    ConfigurationError,
    MiniClaudeError,
    create_client,
    get_api_key,
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
    response = httpx.Response(
        404, request=httpx.Request("POST", "https://x/v1/chat/completions")
    )
    error = APIStatusError("The model does not exist", response=response, body=None)
    service = _service_with(failing_client(error))
    expected = "NVIDIA API error: The model does not exist"
    with pytest.raises(MiniClaudeError, match=expected):
        service.chat_complete(model="nope/nope", messages=[], tools=None)


def test_chat_complete_wraps_connection_error():
    error = APIConnectionError(
        message="failed to connect",
        request=httpx.Request("POST", "https://x"),
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
