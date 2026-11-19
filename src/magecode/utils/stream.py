"""Accumulate OpenAI-compatible streamed chunks into one assistant message.

Providers differ in the fields they stream: Gemini attaches a thought
signature (``extra_content``) to tool-call chunks, while NVIDIA streams
``reasoning_content`` before the final answer. Only ``content`` is shown to the
user; reasoning and signatures are preserved for the follow-up request.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any


def consume_stream(
    stream: Any,
    *,
    on_delta: Callable[[str], None] = lambda _text: None,
) -> Any:
    """Consume *stream*, emitting content deltas and returning a message.

    The returned object has ``role``, ``content`` and ``tool_calls`` fields
    compatible with :func:`core_loop._assistant_message_dict`.
    """
    parts: list[str] = []
    calls: dict[str, dict[str, Any]] = {}
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            continue
        text = getattr(delta, "content", None)
        if text:
            parts.append(text)
            on_delta(text)
        for call in getattr(delta, "tool_calls", None) or []:
            index = getattr(call, "index", None)
            key = str(
                index if index is not None else getattr(call, "id", None) or len(calls)
            )
            entry = calls.setdefault(
                key,
                {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                },
            )
            if getattr(call, "id", None):
                entry["id"] = call.id
            if getattr(call, "type", None):
                entry["type"] = call.type
            extra = getattr(call, "extra_content", None)
            if extra is not None:
                entry["extra_content"] = extra
            function = getattr(call, "function", None)
            if function is not None:
                name = getattr(function, "name", None)
                if name and not entry["function"]["name"]:
                    entry["function"]["name"] = name
                arguments = getattr(function, "arguments", None)
                if arguments:
                    entry["function"]["arguments"] += arguments

    tool_calls = []
    for entry in calls.values():
        function = SimpleNamespace(**entry["function"])
        payload = {
            "id": entry["id"],
            "type": entry["type"],
            "function": function,
        }
        if "extra_content" in entry:
            payload["extra_content"] = entry["extra_content"]
        tool_calls.append(SimpleNamespace(**payload))

    return SimpleNamespace(
        role="assistant",
        content="".join(parts),
        tool_calls=tool_calls,
    )
