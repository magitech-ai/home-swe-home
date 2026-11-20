"""Gemini Interactions API adapter for magitech-harness.

Translates Gemini's native Interactions stream events into mth's ``StreamChunk``
vocabulary (``block-start``, ``text-delta``, ``reasoning-delta``,
``tool-call-delta``, ``usage``, ``finish``). The adapter owns the interaction
lifecycle: it sends the request, consumes the event stream, and yields chunks
that mth's ``AssistantStreamAttempt`` accumulates into a durable assistant
message.

Uses the native Gemini Interactions API for stateful conversations. When a
previous interaction ID is available, it is sent as ``previous_interaction_id``
so Gemini can continue the conversation without resending the full history.

The adapter is registered on ``ctx.llm`` via
``ctx.llm.register_adapter(["gemini"], GeminiAdapter())``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, cast

from magitech_harness.agent.cancellation import AbortSignal
from magitech_harness.llm.adapter_failure import LlmError
from magitech_harness.llm.pi_ai.protocols.common import (
    StreamEmitter,
    finish_chunk,
    map_finish_reason,
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

__all__ = ["GeminiAdapter"]

DEFAULT_MODEL = "gemini-4-hydrogen"

# Known models for listing. The actual model set is fetched dynamically when
# the API key is available; this list is the fallback for offline/test use.
KNOWN_MODELS: tuple[str, ...] = (
    "gemini-4-hydrogen",
    "gemini-3-pro",
    "gemini-2.5-flash",
)


def _api_key() -> str:
    """Resolve the Gemini API key from the environment."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise LlmError(
            "GEMINI_API_KEY is not set. Export it: export GEMINI_API_KEY=<your key>",
            "MISSING_CREDENTIAL",
        )
    return key


class GeminiAdapter(LlmAdapter):
    """Adapter for Google Gemini via the native Interactions API."""

    def __init__(self) -> None:
        super().__init__()
        # Interaction IDs are per-session: the adapter is shared across every
        # agent on the context, so a single field would let two sessions
        # clobber each other's conversation state.
        self._interaction_ids: dict[str, str] = {}

    def provider_info(self, provider: str) -> LlmProviderInfo:
        return {"id": provider, "name": "Google Gemini"}

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
        return {
            "provider": provider,
            "id": model,
            "name": model,
            "reasoning": {
                "efforts": [
                    {"id": "minimal", "name": "Minimal"},
                    {"id": "low", "name": "Low"},
                    {"id": "medium", "name": "Medium"},
                    {"id": "high", "name": "High"},
                ],
                "defaultEffort": "medium",
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
        """Stream mth chunks from the Gemini Interactions API.

        The mth agent loop delivers the system prompt as ``system``-role
        entries in ``messages`` (there is no ``options["system"]``), so the
        system instruction is derived from message history.

        Uses the native Interactions API for stateful conversations. When a
        previous interaction ID is available for this session, it is sent as
        ``previous_interaction_id`` so Gemini can continue the conversation
        without resending the full history.
        """
        api_key = _api_key()
        signal = options.get("signal")
        messages = cast(Sequence[Mapping[str, Any]], options.get("messages") or [])
        tools = cast(Sequence[Mapping[str, Any]] | None, options.get("tools"))
        reasoning_effort = cast(str | None, options.get("reasoningEffort"))
        session_id = cast(str | None, options.get("sessionId"))

        from google import genai

        client = genai.Client(api_key=api_key)

        # Build the request in the Interactions API shape.
        system_instruction = _system_text(messages)
        input_parts = _build_input(messages)
        function_tools = _build_function_tools(tools) or None

        generation_config: dict[str, Any] = {}
        if reasoning_effort:
            generation_config["thinking_level"] = reasoning_effort

        previous_interaction_id = (
            self._interaction_ids.get(session_id) if session_id else None
        )

        params: dict[str, Any] = {
            "model": model,
            "input": input_parts,
            "stream": True,
            "store": True,
        }
        if system_instruction:
            params["system_instruction"] = system_instruction
        if function_tools:
            params["tools"] = function_tools
        if generation_config:
            params["generation_config"] = generation_config
        if previous_interaction_id:
            params["previous_interaction_id"] = previous_interaction_id

        emitter = StreamEmitter()
        finish_reason: str | None = None
        usage_data: dict[str, Any] | None = None
        aborted = False

        try:
            events = client.interactions.create(**params)
            for event in events:
                if signal is not None and signal.is_aborted:
                    aborted = True
                    break

                event_dict = _event_to_dict(event)
                event_type = str(event_dict.get("event_type", ""))

                if event_type == "interaction.created":
                    interaction = event_dict.get("interaction") or {}
                    new_interaction_id = str(interaction.get("id", ""))
                    if new_interaction_id and session_id:
                        self._interaction_ids[session_id] = new_interaction_id
                elif event_type == "interaction.completed":
                    interaction = event_dict.get("interaction") or {}
                    usage_data = dict(interaction.get("usage") or {})
                    finish_reason = "stop"
                    break
                elif event_type == "error":
                    error = event_dict.get("error") or {}
                    raise LlmError(
                        str(error.get("message", "unknown Gemini error")),
                        "PROVIDER_ERROR",
                    )
                elif event_type == "step.delta":
                    delta = event_dict.get("delta") or {}
                    delta_type = str(delta.get("type", ""))
                    if delta_type == "text":
                        text = str(delta.get("text", ""))
                        for chunk in emitter.text(text):
                            yield chunk
                    elif delta_type == "thought_summary":
                        content = delta.get("content")
                        text = _text_from_content(content)
                        for chunk in emitter.reasoning(text):
                            yield chunk
                    elif delta_type == "arguments_delta":
                        args_delta = str(delta.get("arguments", ""))
                        step = event_dict.get("step") or {}
                        call_id = str(step.get("id", ""))
                        call_name = str(step.get("name", ""))
                        for chunk in emitter.tool_call(
                            call_id, call_id, call_name, args_delta
                        ):
                            yield chunk
        finally:
            for chunk in emitter.finalize():
                yield chunk
            if usage_data:
                yield usage_chunk(
                    token_usage(
                        input_tokens=int(usage_data.get("input_tokens", 0)),
                        output_tokens=int(usage_data.get("output_tokens", 0)),
                        total_tokens=int(usage_data.get("total_tokens", 0)),
                    )
                )
            if aborted:
                yield finish_chunk({"kind": "aborted"})
            else:
                yield finish_chunk(map_finish_reason(finish_reason))


def _event_to_dict(event: Any) -> dict[str, Any]:
    """Convert an SDK event object or dict to a plain dict."""
    if isinstance(event, dict):
        return event
    dump = getattr(event, "model_dump", None)
    if callable(dump):
        return dict(dump(exclude_none=True))
    return dict(vars(event)) if hasattr(event, "__dict__") else {}


def _text_from_content(value: Any) -> str:
    """Pull text out of a content block, list of blocks, or string."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("text", "")) if value.get("type", "text") == "text" else ""
    if isinstance(value, list):
        return "".join(_text_from_content(item) for item in value)
    return ""


def _system_text(messages: Sequence[Mapping[str, Any]]) -> str | None:
    """Join every ``system``-role message into one system instruction.

    mth delivers the system prompt as ``system``-role entries in the message
    history — there is no request-level ``system`` option — so this is the
    only place the prompt can be recovered.
    """
    parts = [
        text
        for text in (
            _text_from_content(message.get("content", []))
            for message in messages
            if message.get("role") == "system"
        )
        if text
    ]
    return "\n\n".join(parts) or None


def _tool_name_map(messages: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Map tool-call id -> tool name from assistant message content blocks.

    mth stores tool calls as ``{"type": "tool-call", "id", "name",
    "arguments"}`` blocks inside ``assistant/message`` content. There is no
    ``tool_calls`` array on the message, so the id -> name pairing needed for
    ``function_result.name`` must be read from those blocks.
    """
    names: dict[str, str] = {}
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for block in message.get("content") or []:
            if not isinstance(block, Mapping) or block.get("type") != "tool-call":
                continue
            call_id = str(block.get("id", ""))
            if call_id:
                names[call_id] = str(block.get("name", ""))
    return names


def _build_input(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build the Interactions API ``input`` from mth message history.

    The Interactions API accepts a flat list of content parts. System messages
    are sent via ``system_instruction`` (see :func:`_system_text`), not in
    ``input``. Tool results are sent as ``function_result`` steps. User
    messages are sent as ``text`` parts. Assistant messages with tool calls
    are represented in the interaction history (via
    ``previous_interaction_id``); this function only extracts the new user
    input and any trailing tool results.
    """
    parts: list[dict[str, Any]] = []

    # Find trailing tool-result messages (the new function results to send).
    tail_start = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "tool":
            tail_start = i
        else:
            break

    names = _tool_name_map(messages)

    # Trailing tool results become function_result parts.
    if tail_start < len(messages):
        for message in messages[tail_start:]:
            call_id = str(
                message.get("toolCallId") or message.get("tool_call_id") or ""
            )
            content = message.get("content", "")
            parts.append(
                {
                    "type": "function_result",
                    "name": names.get(call_id, ""),
                    "call_id": call_id,
                    "result": [{"type": "text", "text": str(content)}],
                }
            )
        return parts

    # No tool results — extract the last user message as text input.
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content", "")
            text = _text_from_content(content)
            if text:
                parts.append({"type": "text", "text": text})
            break

    return parts


def _build_function_tools(
    tools: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Convert mth tool schemas to the Interactions API function declaration."""
    if not tools:
        return None
    return [
        {
            "type": "function",
            "name": str(tool.get("name", "")),
            "description": str(tool.get("description", "")),
            "parameters": (
                tool.get("parameters") or {"type": "object", "properties": {}}
            ),
        }
        for tool in tools
    ]
