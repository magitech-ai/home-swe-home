"""OpenRouter Chat Completions adapter for magitech-harness.

Translates OpenRouter's OpenAI-compatible Chat Completions SSE stream into
mth's ``StreamChunk`` vocabulary. Bound to the free, tool-capable model
``particle-ai/particle-1:free`` with ``reasoning.effort = "high"`` (its
catalog default). Reasoning is optional on that model; "high" is retained
as the default effort.

Registered on ctx.llm via
``ctx.llm.register_adapter(["openrouter"], OpenRouterAdapter())``.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, cast

import httpx
from magitech_harness.agent.cancellation import AbortSignal
from magitech_harness.llm.adapter_failure import LlmError
from magitech_harness.llm.pi_ai.protocols.common import (
    StreamEmitter,
    finish_chunk,
    iter_sse_events,
    map_finish_reason,
    parse_json_data,
    token_usage,
    usage_chunk,
)
from magitech_harness.llm.service import LlmAdapter, PreparedAdapterCall
from magitech_harness.llm.types import (
    GenerateOptions,
    LlmModelInfo,
    LlmProviderInfo,
    LlmResolvedModelInfo,
    StreamChunk,
)

__all__ = ["OpenRouterAdapter"]

DEFAULT_MODEL = "particle-ai/particle-1:free"
DEFAULT_REASONING_EFFORT = "high"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# D-009 fail-closed: this adapter is bound to exactly one model. The adapter
# always sends reasoning.effort = "high", so only that effort is advertised.
KNOWN_MODELS: tuple[str, ...] = (DEFAULT_MODEL,)


def _api_key() -> str:
    """Resolve the OpenRouter API key from the environment."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise LlmError(
            "OPENROUTER_API_KEY is not set. Create a key at "
            "https://openrouter.ai/keys, then export it: "
            "export OPENROUTER_API_KEY=<your key>",
            "MISSING_CREDENTIAL",
        )
    return key


class OpenRouterAdapter(LlmAdapter):
    """Adapter for OpenRouter via the OpenAI-compatible Chat Completions API."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def provider_info(self, provider: str) -> LlmProviderInfo:
        return {"id": provider, "name": "OpenRouter"}

    def provider_retry_policy(self, provider: str) -> dict[str, Any] | None:
        return None

    async def list_models(self, provider: str) -> Sequence[LlmModelInfo]:
        try:
            _api_key()
        except LlmError:
            return []
        return [
            {"provider": provider, "id": model_id, "name": model_id}
            for model_id in KNOWN_MODELS
        ]

    async def resolve_model(
        self,
        provider: str,
        model: str,
        signal: AbortSignal | None = None,
    ) -> LlmResolvedModelInfo:
        del signal
        # D-009 fail-closed: only the bound model is known to this adapter.
        if model not in KNOWN_MODELS:
            raise LlmError(
                f"Unknown OpenRouter model {model!r}. Supported: {list(KNOWN_MODELS)}",
                "UNKNOWN_MODEL",
            )
        return {
            "provider": provider,
            "id": model,
            "name": model,
            "reasoning": {
                "efforts": [{"id": "high", "name": "High"}],
                "defaultEffort": DEFAULT_REASONING_EFFORT,
            },
        }

    async def prepare_call(
        self,
        provider: str,
        model: str,
        signal: AbortSignal | None = None,
    ) -> PreparedAdapterCall:
        resolved = await self.resolve_model(provider, model, signal)

        async def _stream(options: GenerateOptions) -> AsyncIterator[StreamChunk]:
            async for chunk in self._stream_call(provider, model, options):
                yield chunk

        return PreparedAdapterCall(model=resolved, stream=_stream)

    def stream(self, options: GenerateOptions) -> AsyncIterator[StreamChunk]:
        provider = str(options.get("provider", ""))
        model = str(options.get("model", ""))

        async def _gen() -> AsyncIterator[StreamChunk]:
            async for chunk in self._stream_call(provider, model, options):
                yield chunk

        return _gen()

    async def _stream_call(
        self,
        provider: str,
        model: str,
        options: GenerateOptions,
    ) -> AsyncIterator[StreamChunk]:
        """Stream mth chunks from OpenRouter Chat Completions SSE."""
        del provider  # model id is bound; provider is metadata only
        api_key = _api_key()
        signal = cast(AbortSignal | None, options.get("signal"))
        messages = cast(Sequence[Mapping[str, Any]], options.get("messages") or [])
        tools = cast(Sequence[Mapping[str, Any]] | None, options.get("tools"))

        body: dict[str, Any] = {
            "model": model or DEFAULT_MODEL,
            "messages": _convert_messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
            # Per OpenRouter docs, reasoning.effort is the unified knob.
            # "high" is the bound model's catalog default.
            "reasoning": {"effort": DEFAULT_REASONING_EFFORT},
        }
        if tools:
            body["tools"] = _convert_tools(tools)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        emitter = StreamEmitter()
        finish_reason: str | None = None
        usage_data: dict[str, Any] | None = None
        aborted = False
        client = self._client or httpx.AsyncClient()

        try:
            async with client.stream(
                "POST",
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=body,
            ) as response:
                if response.status_code >= 400:
                    error_text = await response.aread()
                    raise LlmError(
                        f"OpenRouter error {response.status_code}: "
                        f"{error_text.decode('utf-8', errors='replace')}",
                        "PROVIDER_ERROR",
                        status=response.status_code,
                    )
                async for sse in iter_sse_events(response):
                    if signal is not None and signal.is_aborted:
                        aborted = True
                        break
                    payload = parse_json_data(sse["data"])
                    if payload is None:
                        continue
                    if not isinstance(payload, Mapping):
                        continue
                    if payload.get("error"):
                        error = payload["error"]
                        raise LlmError(
                            str(error.get("message", "unknown OpenRouter error")),
                            "PROVIDER_ERROR",
                        )
                    if payload.get("usage"):
                        usage_data = dict(payload["usage"])
                    choices = payload.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0] if isinstance(choices, list) else None
                    if not isinstance(choice, Mapping):
                        continue
                    if choice.get("finish_reason"):
                        finish_reason = str(choice["finish_reason"])
                    delta = choice.get("delta") or {}
                    if not isinstance(delta, Mapping):
                        continue
                    text = delta.get("content")
                    if text:
                        for chunk in emitter.text(str(text)):
                            yield chunk
                    reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                    if reasoning:
                        for chunk in emitter.reasoning(str(reasoning)):
                            yield chunk
                    tool_calls = delta.get("tool_calls") or []
                    for idx, call in enumerate(tool_calls):
                        if not isinstance(call, Mapping):
                            continue
                        fn = call.get("function") or {}
                        if not isinstance(fn, Mapping):
                            continue
                        call_id = str(call.get("id", ""))
                        name = str(fn.get("name", ""))
                        args_delta = str(fn.get("arguments", ""))
                        # B-2: key on provider index when present, else position.
                        key = str(call.get("index", idx))
                        for chunk in emitter.tool_call(key, call_id, name, args_delta):
                            yield chunk
        finally:
            # m-9: only close an owned client here; terminal chunks belong on
            # the success path (matching the harness's own Chat Completions
            # protocol) so errors are not followed by misleading finish chunks.
            if self._client is None:
                await client.aclose()

        for chunk in emitter.finalize():
            yield chunk
        if usage_data:
            details = usage_data.get("completion_tokens_details") or {}
            reasoning_tokens = (
                int(details.get("reasoning_tokens", 0))
                if isinstance(details, Mapping)
                else 0
            )
            yield usage_chunk(
                token_usage(
                    input_tokens=int(usage_data.get("prompt_tokens", 0)),
                    output_tokens=int(usage_data.get("completion_tokens", 0)),
                    total_tokens=int(usage_data.get("total_tokens", 0)),
                    reasoning_tokens=reasoning_tokens,
                )
            )
        if aborted:
            yield finish_chunk({"kind": "aborted"})
        else:
            yield finish_chunk(map_finish_reason(finish_reason))


def _content_text(content: Any) -> str:
    """Flatten message content blocks to text (mirrors harness flatten_text)."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    if isinstance(content, Sequence):
        for block in content:
            if isinstance(block, Mapping) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
    return "".join(parts)


def _tool_calls_of(content: Any) -> list[dict[str, Any]]:
    """Convert assistant tool-call content blocks to Chat Completions calls (B-1)."""
    calls: list[dict[str, Any]] = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, Mapping) or block.get("type") != "tool-call":
            continue
        arguments = block.get("arguments", "{}")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        calls.append(
            {
                "id": str(block.get("id", "")),
                "type": "function",
                "function": {
                    "name": str(block.get("name", "")),
                    "arguments": arguments,
                },
            }
        )
    return calls


def _convert_messages(
    messages: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Convert mth messages to Chat Completions messages.

    Mirrors the harness's own openai_completions conversion: assistant tool
    calls live in content blocks (not a top-level key), and tool results use
    ``toolCallId`` (with ``tool_call_id`` as fallback).
    """
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", ""))
        content = message.get("content", [])
        if role in ("system", "developer"):
            text = _content_text(content)
            if text:
                converted.append({"role": "system", "content": text})
        elif role == "user":
            converted.append({"role": "user", "content": _content_text(content)})
        elif role == "assistant":
            item: dict[str, Any] = {
                "role": "assistant",
                "content": _content_text(content),
            }
            calls = _tool_calls_of(content)
            if calls:
                item["tool_calls"] = calls
            converted.append(item)
        elif role == "tool":
            tool_call_id = str(
                message.get("toolCallId") or message.get("tool_call_id") or ""
            )
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": _content_text(content) or "(no output)",
                }
            )
    return converted


def _convert_tools(tools: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert mth tools to Chat Completions function tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": str(tool.get("name", "")),
                "description": str(tool.get("description", "")),
                "parameters": tool.get("parameters")
                or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]
