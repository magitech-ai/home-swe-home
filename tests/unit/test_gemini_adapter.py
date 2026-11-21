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
    _system_text,
    _text_from_content,
    _tool_name_map,
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
async def test_prepare_call_streams(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    mock_client = MagicMock()
    mock_client.interactions.create.return_value = iter(
        [{"event_type": "interaction.completed", "interaction": {}}]
    )

    with patch("google.genai.Client", return_value=mock_client):
        adapter = GeminiAdapter()
        prepared = await adapter.prepare_call("gemini", "gemini-4-hydrogen")
        assert prepared.model["id"] == "gemini-4-hydrogen"

        chunks: list[dict[str, Any]] = []
        async for chunk in prepared.stream(
            {"messages": [], "tools": None, "sessionId": "s1"}
        ):
            chunks.append(chunk)
        assert any(c.get("type") == "finish" for c in chunks)


# ---------------------------------------------------------------------------
# _system_text — the system prompt lives in system-role messages
# ---------------------------------------------------------------------------


def test_system_text_from_messages() -> None:
    messages = [
        {"role": "system", "content": [{"type": "text", "text": "SYS"}]},
        {"role": "user", "content": [{"type": "text", "text": "USER"}]},
    ]
    assert _system_text(messages) == "SYS"


def test_system_text_joins_multiple() -> None:
    messages = [
        {"role": "system", "content": [{"type": "text", "text": "A"}]},
        {"role": "system", "content": [{"type": "text", "text": "B"}]},
    ]
    assert _system_text(messages) == "A\n\nB"


def test_system_text_absent() -> None:
    assert _system_text([{"role": "user", "content": "hi"}]) is None


def test_system_text_empty_content() -> None:
    assert _system_text([{"role": "system", "content": []}]) is None


# ---------------------------------------------------------------------------
# _tool_name_map — tool calls live in assistant content blocks
# ---------------------------------------------------------------------------


def test_tool_name_map_from_content_blocks() -> None:
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "calling"},
                {
                    "type": "tool-call",
                    "id": "call_1",
                    "name": "read_file",
                    "arguments": "{}",
                },
            ],
        }
    ]
    assert _tool_name_map(messages) == {"call_1": "read_file"}


def test_tool_name_map_ignores_other_roles() -> None:
    messages = [
        {"role": "user", "content": [{"type": "tool-call", "id": "x", "name": "y"}]}
    ]
    assert _tool_name_map(messages) == {}


def test_tool_name_map_ignores_non_tool_blocks() -> None:
    messages = [{"role": "assistant", "content": [{"type": "text", "text": "hi"}]}]
    assert _tool_name_map(messages) == {}


# ---------------------------------------------------------------------------
# _build_input
# ---------------------------------------------------------------------------


def test_build_input_user_message() -> None:
    messages = [{"role": "user", "content": [{"type": "text", "text": "Hello"}]}]
    parts = _build_input(messages)
    assert len(parts) == 1
    assert parts[0]["type"] == "text"
    assert parts[0]["text"] == "Hello"


def test_build_input_tool_results_resolve_names() -> None:
    """function_result.name comes from the assistant tool-call block."""
    messages = [
        {"role": "user", "content": "Do something"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool-call",
                    "id": "call_1",
                    "name": "read_file",
                    "arguments": '{"path": "/tmp"}',
                }
            ],
        },
        {"role": "tool", "toolCallId": "call_1", "content": "file contents"},
    ]
    parts = _build_input(messages)
    assert len(parts) == 1
    assert parts[0]["type"] == "function_result"
    assert parts[0]["name"] == "read_file"
    assert parts[0]["call_id"] == "call_1"
    assert parts[0]["result"] == [{"type": "text", "text": "file contents"}]


def test_build_input_multiple_tool_results() -> None:
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool-call",
                    "id": "c1",
                    "name": "read_file",
                    "arguments": "{}",
                },
                {
                    "type": "tool-call",
                    "id": "c2",
                    "name": "web_search",
                    "arguments": "{}",
                },
            ],
        },
        {"role": "tool", "toolCallId": "c1", "content": "one"},
        {"role": "tool", "toolCallId": "c2", "content": "two"},
    ]
    parts = _build_input(messages)
    assert [p["name"] for p in parts] == ["read_file", "web_search"]


def test_build_input_no_system_only_messages() -> None:
    assert _build_input([{"role": "system", "content": "You are helpful"}]) == []


def test_build_input_empty_user_text() -> None:
    assert _build_input([{"role": "user", "content": ""}]) == []


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


def test_build_function_tools_no_params() -> None:
    result = _build_function_tools([{"name": "no_params", "description": "No params"}])
    assert result is not None
    assert result[0]["parameters"] == {"type": "object", "properties": {}}


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
        def __init__(self) -> None:
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
    content = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    assert _text_from_content(content) == "ab"


def test_text_from_content_other() -> None:
    assert _text_from_content(42) == ""


# ---------------------------------------------------------------------------
# _stream_call
# ---------------------------------------------------------------------------


def _mock_client(events: list[Any]) -> MagicMock:
    client = MagicMock()
    client.interactions.create.return_value = iter(events)
    return client


@pytest.mark.asyncio
async def test_stream_text_response(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [
        {"event_type": "step.delta", "delta": {"type": "text", "text": "Hello"}},
        {
            "event_type": "interaction.completed",
            "interaction": {"usage": {"input_tokens": 10, "output_tokens": 5}},
        },
    ]
    with patch("google.genai.Client", return_value=_mock_client(events)):
        adapter = GeminiAdapter()
        chunks = [
            c
            async for c in adapter._stream_call(
                "gemini",
                "gemini-4-hydrogen",
                {"messages": [], "tools": None, "sessionId": "s1"},
            )
        ]

    types = [c.get("type") for c in chunks]
    assert "text-delta" in types
    assert "usage" in types
    assert "finish" in types


@pytest.mark.asyncio
async def test_stream_reasoning_response(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [
        {
            "event_type": "step.delta",
            "delta": {"type": "thought_summary", "content": "Thinking..."},
        },
        {"event_type": "interaction.completed", "interaction": {}},
    ]
    with patch("google.genai.Client", return_value=_mock_client(events)):
        adapter = GeminiAdapter()
        chunks = [
            c
            async for c in adapter._stream_call(
                "gemini",
                "gemini-4-hydrogen",
                {"messages": [], "tools": None, "sessionId": "s1"},
            )
        ]

    assert "reasoning-delta" in [c.get("type") for c in chunks]


@pytest.mark.asyncio
async def test_stream_tool_call(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [
        {
            "event_type": "step.delta",
            "step": {"id": "call_1", "name": "read_file"},
            "delta": {"type": "arguments_delta", "arguments": '{"path":"/tmp"}'},
        },
        {"event_type": "interaction.completed", "interaction": {}},
    ]
    with patch("google.genai.Client", return_value=_mock_client(events)):
        adapter = GeminiAdapter()
        chunks = [
            c
            async for c in adapter._stream_call(
                "gemini",
                "gemini-4-hydrogen",
                {"messages": [], "tools": None, "sessionId": "s1"},
            )
        ]

    assert "tool-call-delta" in [c.get("type") for c in chunks]


@pytest.mark.asyncio
async def test_stream_error_event(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [{"event_type": "error", "error": {"message": "Rate limited"}}]
    with patch("google.genai.Client", return_value=_mock_client(events)):
        adapter = GeminiAdapter()
        with pytest.raises(Exception, match="Rate limited"):
            async for _c in adapter._stream_call(
                "gemini",
                "gemini-4-hydrogen",
                {"messages": [], "tools": None, "sessionId": "s1"},
            ):
                pass


@pytest.mark.asyncio
async def test_stream_tracks_interaction_id_per_session(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [
        {"event_type": "interaction.created", "interaction": {"id": "int_123"}},
        {"event_type": "interaction.completed", "interaction": {}},
    ]
    with patch("google.genai.Client", return_value=_mock_client(events)):
        adapter = GeminiAdapter()
        async for _c in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [], "tools": None, "sessionId": "s1"},
        ):
            pass

    assert adapter._interaction_ids["s1"] == "int_123"


@pytest.mark.asyncio
async def test_stream_interaction_ids_are_isolated_by_session(monkeypatch) -> None:
    """Two sessions do not clobber each other's interaction state."""
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [
        {"event_type": "interaction.created", "interaction": {"id": "int_A"}},
        {"event_type": "interaction.completed", "interaction": {}},
    ]
    with patch("google.genai.Client", return_value=_mock_client(events)):
        adapter = GeminiAdapter()
        async for _c in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [], "tools": None, "sessionId": "s1"},
        ):
            pass

    assert adapter._interaction_ids == {"s1": "int_A"}


@pytest.mark.asyncio
async def test_stream_uses_previous_interaction_for_session(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    client = _mock_client([{"event_type": "interaction.completed", "interaction": {}}])

    with patch("google.genai.Client", return_value=client):
        adapter = GeminiAdapter()
        adapter._interaction_ids["s1"] = "prev_123"
        async for _c in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [], "tools": None, "sessionId": "s1"},
        ):
            pass

    sent = client.interactions.create.call_args[1]
    assert sent["previous_interaction_id"] == "prev_123"


@pytest.mark.asyncio
async def test_stream_omits_previous_for_unknown_session(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    client = _mock_client([{"event_type": "interaction.completed", "interaction": {}}])

    with patch("google.genai.Client", return_value=client):
        adapter = GeminiAdapter()
        async for _c in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [], "tools": None, "sessionId": "other"},
        ):
            pass

    assert "previous_interaction_id" not in client.interactions.create.call_args[1]


@pytest.mark.asyncio
async def test_stream_empty_interaction_id_not_recorded(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [
        {"event_type": "interaction.created", "interaction": {}},
        {"event_type": "interaction.completed", "interaction": {}},
    ]
    with patch("google.genai.Client", return_value=_mock_client(events)):
        adapter = GeminiAdapter()
        async for _c in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [], "tools": None, "sessionId": "s1"},
        ):
            pass

    assert "s1" not in adapter._interaction_ids


@pytest.mark.asyncio
async def test_stream_sends_system_instruction_from_messages(monkeypatch) -> None:
    """The system prompt reaches the provider as system_instruction."""
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    client = _mock_client([{"event_type": "interaction.completed", "interaction": {}}])

    messages = [
        {"role": "system", "content": [{"type": "text", "text": "You are hsh."}]},
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
    ]
    with patch("google.genai.Client", return_value=client):
        adapter = GeminiAdapter()
        async for _c in adapter._stream_call(
            "gemini", "gemini-4-hydrogen", {"messages": messages, "sessionId": "s1"}
        ):
            pass

    sent = client.interactions.create.call_args[1]
    assert sent["system_instruction"] == "You are hsh."


@pytest.mark.asyncio
async def test_stream_omits_system_instruction_when_absent(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    client = _mock_client([{"event_type": "interaction.completed", "interaction": {}}])

    with patch("google.genai.Client", return_value=client):
        adapter = GeminiAdapter()
        async for _c in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [{"role": "user", "content": "hi"}], "sessionId": "s1"},
        ):
            pass

    assert "system_instruction" not in client.interactions.create.call_args[1]


@pytest.mark.asyncio
async def test_stream_unknown_event_type(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [
        {"event_type": "some.unknown.event", "data": "ignored"},
        {"event_type": "interaction.completed", "interaction": {}},
    ]
    with patch("google.genai.Client", return_value=_mock_client(events)):
        adapter = GeminiAdapter()
        chunks = [
            c
            async for c in adapter._stream_call(
                "gemini",
                "gemini-4-hydrogen",
                {"messages": [], "tools": None, "sessionId": "s1"},
            )
        ]

    assert "finish" in [c.get("type") for c in chunks]


@pytest.mark.asyncio
async def test_stream_empty_delta_type(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [
        {"event_type": "step.delta", "delta": {}},
        {"event_type": "interaction.completed", "interaction": {}},
    ]
    with patch("google.genai.Client", return_value=_mock_client(events)):
        adapter = GeminiAdapter()
        chunks = [
            c
            async for c in adapter._stream_call(
                "gemini",
                "gemini-4-hydrogen",
                {"messages": [], "tools": None, "sessionId": "s1"},
            )
        ]

    types = [c.get("type") for c in chunks]
    assert "finish" in types
    assert "text-delta" not in types


@pytest.mark.asyncio
async def test_stream_loop_exhausts_without_complete(monkeypatch) -> None:
    """A stream that ends without interaction.completed still finishes."""
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [{"event_type": "step.delta", "delta": {"type": "text", "text": "Hi"}}]
    with patch("google.genai.Client", return_value=_mock_client(events)):
        adapter = GeminiAdapter()
        chunks = [
            c
            async for c in adapter._stream_call(
                "gemini",
                "gemini-4-hydrogen",
                {"messages": [], "tools": None, "sessionId": "s1"},
            )
        ]

    types = [c.get("type") for c in chunks]
    assert "text-delta" in types
    assert "finish" in types


@pytest.mark.asyncio
async def test_stream_abort_yields_aborted_finish(monkeypatch) -> None:
    """Aborting mid-stream finishes with an aborted reason, not a clean stop."""
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    events = [{"event_type": "step.delta", "delta": {"type": "text", "text": "Hi"}}]
    client = _mock_client(events)

    mock_signal = MagicMock()
    mock_signal.is_aborted = True

    with patch("google.genai.Client", return_value=client):
        adapter = GeminiAdapter()
        chunks = [
            c
            async for c in adapter._stream_call(
                "gemini",
                "gemini-4-hydrogen",
                {
                    "messages": [],
                    "tools": None,
                    "sessionId": "s1",
                    "signal": mock_signal,
                },
            )
        ]

    finishes = [c for c in chunks if c.get("type") == "finish"]
    assert len(finishes) == 1
    assert finishes[0]["reason"]["kind"] == "aborted"


@pytest.mark.asyncio
async def test_stream_with_reasoning_effort(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    client = _mock_client([{"event_type": "interaction.completed", "interaction": {}}])

    with patch("google.genai.Client", return_value=client):
        adapter = GeminiAdapter()
        async for _c in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {
                "messages": [],
                "tools": None,
                "sessionId": "s1",
                "reasoningEffort": "high",
            },
        ):
            pass

    config = client.interactions.create.call_args[1]["generation_config"]
    assert config["thinking_level"] == "high"


@pytest.mark.asyncio
async def test_stream_with_tools(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    client = _mock_client([{"event_type": "interaction.completed", "interaction": {}}])

    tools = [
        {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    with patch("google.genai.Client", return_value=client):
        adapter = GeminiAdapter()
        async for _c in adapter._stream_call(
            "gemini",
            "gemini-4-hydrogen",
            {"messages": [], "tools": tools, "sessionId": "s1"},
        ):
            pass

    sent = client.interactions.create.call_args[1]["tools"]
    assert sent[0]["name"] == "read_file"


@pytest.mark.asyncio
async def test_stream_public_method(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    client = _mock_client([{"event_type": "interaction.completed", "interaction": {}}])

    with patch("google.genai.Client", return_value=client):
        adapter = GeminiAdapter()
        chunks = [
            c
            async for c in adapter.stream(
                {
                    "provider": "gemini",
                    "model": "gemini-4-hydrogen",
                    "sessionId": "s1",
                }
            )
        ]

    assert "finish" in [c.get("type") for c in chunks]


def test_build_input_skips_non_user_messages() -> None:
    """The reversed scan skips messages that are not from the user."""
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "the task"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "thinking"}]},
    ]
    parts = _build_input(messages)
    assert len(parts) == 1
    assert parts[0]["text"] == "the task"


def test_tool_name_map_skips_empty_call_id() -> None:
    """A tool-call block with no id is not recorded."""
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool-call", "id": "", "name": "nameless", "arguments": "{}"}
            ],
        }
    ]
    assert _tool_name_map(messages) == {}
