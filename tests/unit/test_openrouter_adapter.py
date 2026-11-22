"""Tests for the OpenRouter Chat Completions adapter."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from home_swe_home.llm.openrouter_adapter import (
    DEFAULT_MODEL,
    OPENROUTER_BASE_URL,
    OpenRouterAdapter,
    _content_text,
    _convert_messages,
    _convert_tools,
)


def _sse(frames: list[dict]) -> bytes:
    """Encode payloads as an OpenAI-style SSE stream."""
    lines: list[str] = []
    for frame in frames:
        lines.append(f"data: {json.dumps(frame)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def test_constants() -> None:
    assert DEFAULT_MODEL == "tencent/hy4-flash"
    assert OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"


def test_missing_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from home_swe_home.llm.openrouter_adapter import _api_key

    with pytest.raises(Exception, match="OPENROUTER_API_KEY is not set"):
        _api_key()


async def test_api_key_present() -> None:
    from home_swe_home.llm.openrouter_adapter import _api_key

    assert _api_key() == "test-key"


def test_provider_info() -> None:
    adapter = OpenRouterAdapter()
    info = adapter.provider_info("openrouter")
    assert info == {"id": "openrouter", "name": "OpenRouter"}
    assert adapter.provider_retry_policy("openrouter") is None


async def test_list_models_with_key() -> None:
    adapter = OpenRouterAdapter()
    models = await adapter.list_models("openrouter")
    assert len(models) == 1
    assert models[0]["id"] == DEFAULT_MODEL
    assert models[0]["provider"] == "openrouter"


async def test_list_models_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    adapter = OpenRouterAdapter()
    assert await adapter.list_models("openrouter") == []


async def test_resolve_model() -> None:
    adapter = OpenRouterAdapter()
    result = await adapter.resolve_model("openrouter", DEFAULT_MODEL)
    assert result["id"] == DEFAULT_MODEL
    assert result["reasoning"]["efforts"] == [{"id": "high", "name": "High"}]
    assert result["reasoning"]["defaultEffort"] == "high"


async def test_resolve_unknown_model_fails_closed() -> None:
    adapter = OpenRouterAdapter()
    with pytest.raises(Exception, match="Unknown OpenRouter model"):
        await adapter.resolve_model("openrouter", "some/other-model")


def test_content_text_helpers() -> None:
    assert _content_text("hello") == "hello"
    assert (
        _content_text([{"type": "text", "text": "a"}, {"type": "x", "text": "b"}])
        == "a"
    )
    assert _content_text(123) == ""


def test_convert_messages() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "developer", "content": "dev"},
        {"role": "user", "content": "hi"},
        # B-1: assistant tool call is a content block, not a top-level key.
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "yo"},
                {
                    "type": "tool-call",
                    "id": "call-1",
                    "name": "read_file",
                    "arguments": {"path": "x"},
                },
            ],
        },
        {"role": "tool", "toolCallId": "call-1", "content": "result"},
        {"role": "tool", "tool_call_id": "call-2", "content": ""},
        {"role": "weird", "content": "x"},
    ]
    converted = _convert_messages(messages)
    assert converted[0] == {"role": "system", "content": "sys"}
    assert converted[1] == {"role": "system", "content": "dev"}
    assert converted[2] == {"role": "user", "content": "hi"}
    assert converted[3]["role"] == "assistant"
    assert converted[3]["content"] == "yo"
    assert converted[3]["tool_calls"][0]["id"] == "call-1"
    assert converted[3]["tool_calls"][0]["function"]["name"] == "read_file"
    assert '"path"' in converted[3]["tool_calls"][0]["function"]["arguments"]
    # assistant without tool-call block
    plain = _convert_messages([{"role": "assistant", "content": "ok"}])
    assert plain == [{"role": "assistant", "content": "ok"}]
    # B-1: toolCallId preferred, fallback to tool_call_id, empty -> "(no output)"
    assert converted[4]["role"] == "tool"
    assert converted[4]["tool_call_id"] == "call-1"
    assert converted[5]["tool_call_id"] == "call-2"
    assert converted[5]["content"] == "(no output)"
    # Unknown roles are silently dropped (matches harness conversion).
    assert len(converted) == 6
    # String arguments stay as-is; empty system text is skipped.
    extra = _convert_messages(
        [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool-call", "id": "c", "name": "n", "arguments": "{}"}
                ],
            },
            {"role": "system", "content": ""},
        ]
    )
    assert extra[0]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert len(extra) == 1


def test_convert_tools() -> None:
    tools = [{"name": "t", "description": "d", "parameters": {"type": "object"}}]
    converted = _convert_tools(tools)
    assert converted[0]["type"] == "function"
    assert converted[0]["function"]["name"] == "t"
    assert _convert_tools([{"name": "x"}])[0]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
    }


async def test_prepare_call() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(
                [
                    {
                        "choices": [
                            {
                                "delta": {"content": "hello"},
                                "finish_reason": None,
                            }
                        ]
                    },
                    {
                        "choices": [
                            {"delta": {"content": ""}, "finish_reason": "stop"}
                        ],
                        "usage": {
                            "prompt_tokens": 5,
                            "completion_tokens": 3,
                            "total_tokens": 8,
                        },
                    },
                ]
            ),
        )

    adapter = OpenRouterAdapter(client=_client(handler))
    prepared = await adapter.prepare_call("openrouter", DEFAULT_MODEL)
    assert prepared.model["id"] == DEFAULT_MODEL
    chunks = [c async for c in prepared.stream({"messages": []})]
    types = [c["type"] for c in chunks]
    assert "block-start" in types
    assert "text-delta" in types
    assert "usage" in types
    assert "finish" in types
    assert chunks[-1]["reason"] == {"kind": "stop"}
    assert seen["url"].endswith("/chat/completions")
    assert seen["body"]["reasoning"] == {"effort": "high"}
    assert seen["body"]["stream"] is True
    assert seen["body"]["stream_options"] == {"include_usage": True}


async def test_stream_text_reasoning_tool_and_usage() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        frames = [
            {
                "choices": [
                    {
                        "delta": {
                            "content": "Hi",
                            "reasoning": "think",
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "function": {
                                        "name": "do_it",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 6,
                    "total_tokens": 16,
                    "completion_tokens_details": {"reasoning_tokens": 2},
                },
            },
        ]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(frames),
        )

    adapter = OpenRouterAdapter(client=_client(handler))
    chunks = [
        c
        async for c in adapter.stream(
            {
                "provider": "openrouter",
                "model": DEFAULT_MODEL,
                "messages": [{"role": "user", "content": "go"}],
                "tools": [{"name": "do_it", "description": "d", "parameters": {}}],
            }
        )
    ]
    text = "".join(c.get("text", "") for c in chunks if c["type"] == "text-delta")
    reasoning = "".join(
        c.get("text", "") for c in chunks if c["type"] == "reasoning-delta"
    )
    assert text == "Hi"
    assert reasoning == "think"
    assert any(c["type"] == "tool-call-delta" for c in chunks)
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["tools"][0]["type"] == "function"
    usage = next(c for c in chunks if c["type"] == "usage")
    assert usage["usage"]["reasoningTokens"] == 2
    assert chunks[-1]["reason"] == {"kind": "tool-calls"}


async def test_stream_error_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse([{"error": {"message": "bad request"}}]).replace(
                b'"error"', b'"error"', 1
            ),
        )

    adapter = OpenRouterAdapter(client=_client(handler))
    with pytest.raises(Exception, match="bad request"):
        [c async for c in adapter.stream({"model": DEFAULT_MODEL, "messages": []})]


async def test_stream_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, content=b"credits depleted")

    adapter = OpenRouterAdapter(client=_client(handler))
    with pytest.raises(Exception, match="OpenRouter error 402"):
        [c async for c in adapter.stream({"model": DEFAULT_MODEL, "messages": []})]


async def test_stream_non_mapping_payload_and_tool_edges() -> None:
    """Cover defensive branches: non-Mapping payload, tool call, and function."""

    def handler(request: httpx.Request) -> httpx.Response:
        content = (
            b'data: "just a string"\n\n'
            b'data: {"choices": [{"delta": {"tool_calls": '
            b'["bad", {"function": "bad"}]}}]}\n\n'
        )
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=content
        )

    adapter = OpenRouterAdapter(client=_client(handler))
    chunks = [c async for c in adapter.stream({"model": DEFAULT_MODEL, "messages": []})]
    assert chunks[-1]["reason"] == {"kind": "stop"}


async def test_stream_aborted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse([{"choices": [{"delta": {"content": "x"}}]}]),
        )

    signal = MagicMock()
    signal.is_aborted = True
    adapter = OpenRouterAdapter(client=_client(handler))
    chunks = [
        c
        async for c in adapter.stream(
            {"model": DEFAULT_MODEL, "messages": [], "signal": signal}
        )
    ]
    assert chunks[-1]["reason"] == {"kind": "aborted"}


async def test_stream_skips_malformed_frames() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = (
            b"data: not-json\n\n"
            b"data: [DONE]\n\n"
            b'data: {"choices": []}\n\n'
            b'data: {"choices": "bad"}\n\n'
            b'data: {"choices": [{"delta": "bad"}]}\n\n'
        )
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=content
        )

    adapter = OpenRouterAdapter(client=_client(handler))
    chunks = [c async for c in adapter.stream({"model": DEFAULT_MODEL, "messages": []})]
    assert chunks[-1]["reason"] == {"kind": "stop"}


async def test_stream_defaults_model_and_closes_owned_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no injected client the adapter creates and closes its own."""
    created: dict = {}

    class FakeClient:
        def __init__(self) -> None:
            created["made"] = True

        def stream(self, *args, **kwargs):
            raise RuntimeError("stop before network")

        async def aclose(self) -> None:
            created["closed"] = True

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    adapter = OpenRouterAdapter()
    with pytest.raises(RuntimeError, match="stop before network"):
        [c async for c in adapter.stream({"messages": []})]
    assert created.get("made") is True
    assert created.get("closed") is True


async def test_tool_call_index_correlation() -> None:
    """B-2: multiple tool calls use provider 'index', not enumerate position."""

    def handler(request: httpx.Request) -> httpx.Response:
        frames = [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-a",
                                    "function": {"name": "first", "arguments": ""},
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 1,
                                    "id": "call-b",
                                    "function": {"name": "second", "arguments": ""},
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": '{"x":1}'},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        ]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(frames),
        )

    adapter = OpenRouterAdapter(client=_client(handler))
    chunks = [c async for c in adapter.stream({"model": DEFAULT_MODEL, "messages": []})]
    block_ends = [
        c["block"]
        for c in chunks
        if c["type"] == "block-end" and c["block"]["type"] == "tool-call"
    ]
    assert len(block_ends) == 2
    assert block_ends[0]["id"] == "call-a"
    assert block_ends[0]["name"] == "first"
    assert block_ends[0]["arguments"] == '{"x":1}'
    assert block_ends[1]["id"] == "call-b"
    assert block_ends[1]["name"] == "second"


async def test_terminal_chunks_not_emitted_on_error() -> None:
    """m-9: errors do not emit misleading finish/usage chunks."""

    def handler(request: httpx.Request) -> httpx.Response:
        frames = [{"error": {"message": "boom"}}]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(frames),
        )

    adapter = OpenRouterAdapter(client=_client(handler))
    collected: list[dict] = []
    with pytest.raises(Exception, match="boom"):
        async for chunk in adapter.stream({"model": DEFAULT_MODEL, "messages": []}):
            collected.append(chunk)
    # No misleading terminal chunks should be emitted before the error.
    assert not any(c["type"] in {"finish", "usage", "block-end"} for c in collected)
