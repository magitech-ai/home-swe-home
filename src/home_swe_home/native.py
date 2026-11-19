"""Gemini Interactions API adapter for the home-swe-home turn loop."""

from __future__ import annotations

from typing import Any

from .contracts import (
    FunctionResult,
    FunctionTool,
    NativeGenerationConfig,
    NativeRequest,
    TextContent,
)
from .utils.native_events import NativeTranslator


def native_tool_models(tools: list[dict[str, Any]] | None) -> list[FunctionTool]:
    """Convert OpenAI tool schemas to validated Interactions function models."""
    result: list[FunctionTool] = []
    for tool in tools or []:
        function = tool.get("function", {})
        result.append(
            FunctionTool(
                type="function",
                name=function.get("name", ""),
                description=function.get("description", ""),
                parameters=function.get("parameters", {}),
            )
        )
    return result


def native_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Convert OpenAI tool schemas to the Interactions API `Function` shape."""
    return [declared.model_dump() for declared in native_tool_models(tools)]


def native_system_instruction(messages: list[dict[str, Any]]) -> str:
    """Return the first system message content, for the API's system field.

    The Interactions API has a dedicated top-level ``system_instruction``
    parameter. Sending this text inside ``input`` would make it user content,
    losing its instruction priority. Keep it out of ``input`` entirely.
    """
    for message in messages:
        if message.get("role") == "system":
            return str(message.get("content", ""))
    return ""


def native_input(
    messages: list[dict[str, Any]], *, has_interaction: bool
) -> tuple[Any, list[dict[str, Any]]]:
    """Build the native `input` and any client-side function results."""
    results: list[dict[str, Any]] = []
    names: dict[str, str] = {}
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function", {})
            names[call.get("id", "")] = function.get("name", "")
    tail = 0
    for message in reversed(messages):
        if message.get("role") != "tool":
            break
        tail += 1
    if tail and has_interaction:
        for message in messages[-tail:]:
            declared = FunctionResult(
                type="function_result",
                name=names.get(message.get("tool_call_id", ""), ""),
                call_id=message.get("tool_call_id", ""),
                result=[TextContent(type="text", text=str(message.get("content", "")))],
            )
            results.append(declared.model_dump())
        return results, results

    parts: list[dict[str, str]] = []
    for message in reversed(messages):
        if message.get("role") == "user":
            parts.append(
                TextContent(
                    type="text", text=str(message.get("content", ""))
                ).model_dump()
            )
            break
    return parts, results


def native_stream(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    reasoning: bool,
    interaction_id: str | None,
    on_interaction: Any,
    effort: str = "medium",
) -> Any:
    """Yield OpenAI-shaped chunks from a native Interactions stream."""
    current, _ = native_input(messages, has_interaction=bool(interaction_id))
    system_instruction = native_system_instruction(messages) or None
    generation = NativeGenerationConfig(
        thinking_level=effort,
        thinking_summaries="auto" if reasoning else None,
    )
    request = NativeRequest(
        model=model,
        input=current,
        system_instruction=system_instruction,
        tools=native_tool_models(tools) or None,
        stream=True,
        store=True,
        previous_interaction_id=interaction_id,
        generation_config=generation,
    )
    params: dict[str, Any] = request.wire()

    translator = NativeTranslator(
        on_interaction=on_interaction,
        on_call=lambda call: pending.append(_call_chunk(call)),
    )
    pending: list[Any] = []

    def on_content(text: str) -> None:
        pending.append(_delta_chunk(content=text))

    def on_reasoning(text: str) -> None:
        pending.append(_delta_chunk(reasoning=text))

    def on_event(event: Any) -> None:
        pending.append(_event_chunk(event))

    translator._on_content = on_content
    translator._on_reasoning = on_reasoning
    translator._on_event = on_event

    events = client.interactions.create(**params)
    for event in events:
        pending.clear()
        translator.feed(event)
        for chunk in pending:
            yield chunk


def _delta_chunk(*, content: str = "", reasoning: str = "") -> Any:
    from types import SimpleNamespace

    delta = SimpleNamespace(
        content=content or None,
        reasoning_content=reasoning or None,
        tool_calls=None,
        event=None,
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _call_chunk(call: dict[str, Any]) -> Any:
    from types import SimpleNamespace

    function = SimpleNamespace(name=call["name"], arguments=call["arguments"])
    tool = SimpleNamespace(
        index=call.get("index", 0),
        id=call["id"],
        type="function",
        function=function,
        extra_content=None,
    )
    delta = SimpleNamespace(
        content=None, reasoning_content=None, tool_calls=[tool], event=None
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _event_chunk(event: Any) -> Any:
    from types import SimpleNamespace

    delta = SimpleNamespace(
        content=None, reasoning_content=None, tool_calls=None, event=event
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])
