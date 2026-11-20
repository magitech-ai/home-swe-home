"""Tests for the GeminiAdapter."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from home_swe_home.llm.gemini_adapter import (
    KNOWN_MODELS,
    GeminiAdapter,
    _api_key,
    _build_function_tools,
    _build_input,
    _event_to_dict,
    _text_from_content,
)

# ---------------------------------------------------------------------------
# _api_key
# ---------------------------------------------------------------------------


def test_api_key_from_gemini(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key123")
    assert _api_key() == "key123"


def test_api_key_from_google(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "gkey456")
    assert _api_key() == "gkey456"


def test_api_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(Exception, match="GEMINI_API_KEY is not set"):
        _api_key()


# ---------------------------------------------------------------------------
# provider_info / provider_retry_policy
# ---------------------------------------------------------------------------


def test_provider_info() -> None:
    adapter = GeminiAdapter()
    info = adapter.provider_info("gemini")
    assert info["id"] == "gemini"
    assert info["name"] == "Google Gemini"


def test_provider_retry_policy() -> None:
    adapter = GeminiAdapter()
    assert adapter.provider_retry_policy("gemini") is None


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models_with_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    adapter = GeminiAdapter()
    models = await adapter.list_models("gemini")
    assert len(models) == len(KNOWN_MODELS)
    assert models[0]["provider"] == "gemini"


@pytest.mark.asyncio
async def test_list_models_without_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    adapter = GeminiAdapter()
    models = await adapter.list_models("gemini")
    assert models == []


# ---------------------------------------------------------------------------
# resolve_model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_model() -> None:
    adapter = GeminiAdapter()
    result = await adapter.resolve_model("gemini", "gemini-4-hydrogen")
    assert result["provider"] == "gemini"
    assert result["id"] == "gemini-4-hydrogen"
    assert "reasoning" in result
    assert len(result["reasoning"]["efforts"]) == 4


# ---------------------------------------------------------------------------
# prepare_call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_call(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter([mock_event_done])

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        prepared = await adapter.prepare_call("gemini", "gemini-4-hydrogen")
        assert prepared.model["id"] == "gemini-4-hydrogen"

        # Consume the stream to cover the closure.
        chunks: list[dict[str, Any]] = []
        async for chunk in prepared.stream({"messages": [], "tools": None}):
            chunks.append(chunk)
        assert any(c.get("type") == "finish" for c in chunks)


# ---------------------------------------------------------------------------
# stream (via _stream_call)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_text_response(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_text = {
        "event_type": "step.delta",
        "delta": {"type": "text", "text": "Hello"},
    }
    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {"usage": {"input_tokens": 10, "output_tokens": 5}},
    }

    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter(
        [mock_event_text, mock_event_done]
    )

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        chunks: list[dict[str, Any]] = []
        async for chunk in adapter._stream_call(
            "gemini", "gemini-4-hydrogen", {"messages": [], "tools": None}
        ):
            chunks.append(chunk)

    # Should have text-delta, block-end, usage, finish
    types = [c.get("type") for c in chunks]
    assert "text-delta" in types
    assert "finish" in types


@pytest.mark.asyncio
async def test_stream_reasoning_response(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_reasoning = {
        "event_type": "step.delta",
        "delta": {"type": "thought_summary", "content": "Thinking..."},
    }
    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }

    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter(
        [mock_event_reasoning, mock_event_done]
    )

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        chunks: list[dict[str, Any]] = []
        async for chunk in adapter._stream_call(
            "gemini", "gemini-4-hydrogen", {"messages": [], "tools": None}
        ):
            chunks.append(chunk)

    types = [c.get("type") for c in chunks]
    assert "reasoning-delta" in types


@pytest.mark.asyncio
async def test_stream_tool_call(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_tool = {
        "event_type": "step.delta",
        "step": {"id": "call_1", "name": "read_file"},
        "delta": {"type": "arguments_delta", "arguments": '{"path":"/tmp"}'},
    }
    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }

    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter(
        [mock_event_tool, mock_event_done]
    )

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        chunks: list[dict[str, Any]] = []
        async for chunk in adapter._stream_call(
            "gemini", "gemini-4-hydrogen", {"messages": [], "tools": None}
        ):
            chunks.append(chunk)

    types = [c.get("type") for c in chunks]
    assert "tool-call-delta" in types


@pytest.mark.asyncio
async def test_stream_error_event(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_error = {
        "event_type": "error",
        "error": {"message": "Rate limited"},
    }

    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter([mock_event_error])

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        with pytest.raises(Exception, match="Rate limited"):
            async for _chunk in adapter._stream_call(
                "gemini", "gemini-4-hydrogen", {"messages": [], "tools": None}
            ):
                pass


@pytest.mark.asyncio
async def test_stream_with_interaction_id(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_created = {
        "event_type": "interaction.created",
        "interaction": {"id": "int_123"},
    }
    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }

    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter(
        [mock_event_created, mock_event_done]
    )

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        async for _chunk in adapter._stream_call(
            "gemini", "gemini-4-hydrogen", {"messages": [], "tools": None}
        ):
            pass

    assert adapter._interaction_id == "int_123"


@pytest.mark.asyncio
async def test_stream_uses_previous_interaction(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }

    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter([mock_event_done])

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        adapter._interaction_id = "prev_123"
        async for _chunk in adapter._stream_call(
            "gemini", "gemini-4-hydrogen", {"messages": [], "tools": None}
        ):
            pass

    # Verify previous_interaction_id was passed
    call_kwargs = mock_client.interactions.create.call_args[1]
    assert call_kwargs.get("previous_interaction_id") == "prev_123"


@pytest.mark.asyncio
async def test_stream_with_abort_signal(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event = {
        "event_type": "step.delta",
        "delta": {"type": "text", "text": "Hello"},
    }
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter([mock_event])

    mock_signal = MagicMock()
    mock_signal.is_aborted = True

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        chunks: list[dict[str, Any]] = []
        async for chunk in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [], "tools": None, "signal": mock_signal},
        ):
            chunks.append(chunk)

    # The finally block always emits a finish chunk, even on abort.
    # But no content chunks should be emitted.
    types = [c.get("type") for c in chunks]
    assert "text-delta" not in types
    assert "finish" in types


@pytest.mark.asyncio
async def test_stream_with_reasoning_effort(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter([mock_event_done])

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        async for _chunk in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [], "tools": None, "reasoningEffort": "high"},
        ):
            pass

    call_kwargs = mock_client.interactions.create.call_args[1]
    assert call_kwargs["generation_config"]["thinking_level"] == "high"


@pytest.mark.asyncio
async def test_stream_with_unknown_event_type(monkeypatch) -> None:
    """Unknown event types are silently ignored."""
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_unknown = {"event_type": "some.unknown.event", "data": "ignored"}
    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter(
        [mock_event_unknown, mock_event_done]
    )

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        chunks: list[dict[str, Any]] = []
        async for chunk in adapter._stream_call(
            "gemini", "gemini-4-hydrogen", {"messages": [], "tools": None}
        ):
            chunks.append(chunk)

    types = [c.get("type") for c in chunks]
    assert "finish" in types


@pytest.mark.asyncio
async def test_stream_with_empty_interaction_id(monkeypatch) -> None:
    """An interaction.created event with no ID doesn't set _interaction_id."""
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_created = {
        "event_type": "interaction.created",
        "interaction": {},
    }
    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter(
        [mock_event_created, mock_event_done]
    )

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        async for _chunk in adapter._stream_call(
            "gemini", "gemini-4-hydrogen", {"messages": [], "tools": None}
        ):
            pass

    # _interaction_id should not be set to an empty string
    assert adapter._interaction_id is None


@pytest.mark.asyncio
async def test_stream_with_empty_delta_type(monkeypatch) -> None:
    """A step.delta with an empty delta type is ignored."""
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_empty = {
        "event_type": "step.delta",
        "delta": {},
    }
    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter(
        [mock_event_empty, mock_event_done]
    )

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        chunks: list[dict[str, Any]] = []
        async for chunk in adapter._stream_call(
            "gemini", "gemini-4-hydrogen", {"messages": [], "tools": None}
        ):
            chunks.append(chunk)

    types = [c.get("type") for c in chunks]
    # No text/reasoning/tool chunks, just finish
    assert "finish" in types
    assert "text-delta" not in types


@pytest.mark.asyncio
async def test_stream_loop_exhausts_without_complete(monkeypatch) -> None:
    """Loop exhausts without interaction.completed — still emits finish."""
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    # Only a text event, no interaction.completed
    mock_event_text = {
        "event_type": "step.delta",
        "delta": {"type": "text", "text": "Hello"},
    }
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter([mock_event_text])

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        chunks: list[dict[str, Any]] = []
        async for chunk in adapter._stream_call(
            "gemini", "gemini-4-hydrogen", {"messages": [], "tools": None}
        ):
            chunks.append(chunk)

    types = [c.get("type") for c in chunks]
    assert "text-delta" in types
    assert "finish" in types


@pytest.mark.asyncio
async def test_stream_with_tools(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter([mock_event_done])

    tools = [
        {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {"type": "object", "properties": {}},
        }
    ]

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        async for _chunk in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [], "tools": tools},
        ):
            pass

    call_kwargs = mock_client.interactions.create.call_args[1]
    assert call_kwargs["tools"] is not None
    assert call_kwargs["tools"][0]["name"] == "read_file"


@pytest.mark.asyncio
async def test_stream_with_system(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter([mock_event_done])

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        async for _chunk in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [], "tools": None, "system": "You are helpful"},
        ):
            pass

    call_kwargs = mock_client.interactions.create.call_args[1]
    assert call_kwargs["system_instruction"] == "You are helpful"


# ---------------------------------------------------------------------------
# _event_to_dict
# ---------------------------------------------------------------------------


def test_event_to_dict_dict() -> None:
    assert _event_to_dict({"a": 1}) == {"a": 1}


def test_event_to_dict_model_dump() -> None:
    event = MagicMock()
    event.model_dump.return_value = {"b": 2}
    assert _event_to_dict(event) == {"b": 2}


def test_event_to_dict_vars() -> None:
    class Ev:
        def __init__(self):
            self.c = 3

    assert _event_to_dict(Ev()) == {"c": 3}


def test_event_to_dict_empty() -> None:
    assert _event_to_dict("string") == {}


# ---------------------------------------------------------------------------
# _text_from_content
# ---------------------------------------------------------------------------


def test_text_from_content_string() -> None:
    assert _text_from_content("hello") == "hello"


def test_text_from_content_dict() -> None:
    assert _text_from_content({"type": "text", "text": "hi"}) == "hi"
    assert _text_from_content({"type": "image", "text": "skip"}) == ""


def test_text_from_content_list() -> None:
    assert (
        _text_from_content(
            [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        )
        == "ab"
    )


def test_text_from_content_other() -> None:
    assert _text_from_content(42) == ""


# ---------------------------------------------------------------------------
# _build_input
# ---------------------------------------------------------------------------


def test_build_input_user_message() -> None:
    messages = [{"role": "user", "content": [{"type": "text", "text": "Hello"}]}]
    parts = _build_input(messages)
    assert len(parts) == 1
    assert parts[0]["type"] == "text"
    assert parts[0]["text"] == "Hello"


def test_build_input_tool_results() -> None:
    messages = [
        {"role": "user", "content": "Do something"},
        {
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "toolCallId": "call_1",
            "content": "file contents here",
        },
    ]
    parts = _build_input(messages)
    assert len(parts) == 1
    assert parts[0]["type"] == "function_result"
    assert parts[0]["name"] == "read_file"
    assert parts[0]["call_id"] == "call_1"


def test_build_input_no_user_message() -> None:
    messages = [{"role": "system", "content": "You are helpful"}]
    parts = _build_input(messages)
    assert parts == []


def test_build_input_empty_user_text() -> None:
    """A user message with empty text produces no input parts."""
    messages = [{"role": "user", "content": ""}]
    parts = _build_input(messages)
    assert parts == []


def test_build_input_tail_with_non_tool() -> None:
    """A non-tool message at the end breaks the tool-result tail scan."""
    messages = [
        {"role": "user", "content": "Do something"},
        {
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "toolCallId": "call_1",
            "content": "file contents",
        },
        # A non-tool message at the end breaks the tail scan.
        {"role": "user", "content": "Thanks!"},
    ]
    parts = _build_input(messages)
    # The tail scan breaks at the user message, so no tool results are found.
    # Falls through to extracting the last user message as text input.
    assert len(parts) == 1
    assert parts[0]["type"] == "text"
    assert parts[0]["text"] == "Thanks!"


# ---------------------------------------------------------------------------
# _build_function_tools
# ---------------------------------------------------------------------------


def test_build_function_tools_none() -> None:
    assert _build_function_tools(None) is None


def test_build_function_tools_empty() -> None:
    assert _build_function_tools([]) is None


def test_build_function_tools() -> None:
    tools = [
        {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    result = _build_function_tools(tools)
    assert result is not None
    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert result[0]["name"] == "read_file"
    assert result[0]["description"] == "Read a file"


def test_build_function_tools_no_params() -> None:
    tools = [{"name": "no_params", "description": "No params"}]
    result = _build_function_tools(tools)
    assert result is not None
    assert result[0]["parameters"] == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# stream (public method)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_public_method(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_event_done = {
        "event_type": "interaction.completed",
        "interaction": {},
    }
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter([mock_event_done])

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        chunks: list[dict[str, Any]] = []
        async for chunk in adapter.stream(
            {"provider": "gemini", "model": "gemini-4-hydrogen"}
        ):
            chunks.append(chunk)

    types = [c.get("type") for c in chunks]
    assert "finish" in types
