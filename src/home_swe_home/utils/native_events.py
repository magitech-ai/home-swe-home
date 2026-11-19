"""Translate Gemini Interactions API events into home-swe-home's message shape.

Every event is recorded. Known event and delta types are mapped to content,
reasoning, tool calls or structured events; unknown types are kept and flagged
so a new upstream event is visible rather than silently discarded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable

EVENT_TYPES = frozenset(
    {
        "interaction.created",
        "interaction.status_update",
        "step.start",
        "step.delta",
        "step.stop",
        "interaction.completed",
        "error",
        "done",
    }
)

DELTA_TYPES = frozenset(
    {
        "arguments_delta",
        "audio",
        "code_execution_call",
        "code_execution_result",
        "document",
        "file_search_call",
        "file_search_result",
        "function_result",
        "google_maps_call",
        "google_maps_result",
        "google_search_call",
        "google_search_result",
        "image",
        "mcp_server_tool_call",
        "mcp_server_tool_result",
        "processing_call",
        "processing_result",
        "text",
        "text_annotation_delta",
        "thought_signature",
        "thought_summary",
        "url_context_call",
        "url_context_result",
        "video",
    }
)


def as_dict(event: Any) -> dict[str, Any]:
    """Accept SDK event objects or plain dicts."""
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


def _summary(value: Any) -> dict[str, Any]:
    """Keep a small, non-binary view of an event payload."""
    if not isinstance(value, dict):
        return {"value": str(value)[:120]}
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"data", "result", "signature", "annotations"}:
            result[key] = f"<{len(str(item))} chars>"
        elif isinstance(item, (str, int, float, bool)) or item is None:
            result[key] = item
    return result


@dataclass(frozen=True)
class NativeEvent:
    """One observed event, with its delta type and a safe payload summary."""

    event_type: str
    known: bool
    step_index: int | None = None
    step_type: str | None = None
    delta_type: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        parts = [self.event_type]
        if self.delta_type:
            parts.append(self.delta_type)
        if self.step_type:
            parts.append(self.step_type)
        return ":".join(parts)


@dataclass
class NativeTurn:
    """The assembled result of one native interaction stream."""

    interaction_id: str = ""
    content: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    events: list[NativeEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = ""
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def unknown(self) -> tuple[str, ...]:
        """Labels of events/deltas this client does not yet understand."""
        return tuple(event.label() for event in self.events if not event.known)

    def on_content(self, text: str) -> None:
        self.content += text

    def on_reasoning(self, text: str) -> None:
        self.reasoning += text

    def on_event(self, event: NativeEvent) -> None:
        self.events.append(event)


class NativeTranslator:
    """Feed events in, emit a :class:`NativeTurn` and optional live hooks."""

    def __init__(
        self,
        *,
        on_content: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        on_event: Callable[[NativeEvent], None] | None = None,
        on_interaction: Callable[[str], None] | None = None,
        on_call: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.turn = NativeTurn()
        self._on_content = on_content
        self._on_reasoning = on_reasoning
        self._on_event = on_event
        self._on_interaction = on_interaction
        self._on_call = on_call
        self._current_call: dict[str, Any] | None = None
        self._call_index = 0

    def feed(self, event: Any) -> None:
        """Translate one SDK event or dict."""
        payload = as_dict(event)
        event_type = str(payload.get("event_type", ""))
        known_event = event_type in EVENT_TYPES
        index = payload.get("index")
        step = payload.get("step") or {}
        step_type = str(step.get("type", "")) if isinstance(step, dict) else ""
        delta = payload.get("delta") or {}
        delta_type = str(delta.get("type", "")) if isinstance(delta, dict) else ""

        record = NativeEvent(
            event_type=event_type,
            known=known_event and (not delta_type or delta_type in DELTA_TYPES),
            step_index=index if isinstance(index, int) else None,
            step_type=step_type or None,
            delta_type=delta_type or None,
            detail=_summary(delta or step or payload.get("interaction") or payload),
        )
        self.turn.on_event(record)
        if self._on_event:
            self._on_event(record)

        if event_type == "interaction.created":
            interaction = payload.get("interaction") or {}
            self.turn.interaction_id = str(interaction.get("id", ""))
            if self._on_interaction:
                self._on_interaction(self.turn.interaction_id)
        elif event_type in {"interaction.status_update", "interaction.completed"}:
            interaction = payload.get("interaction") or {}
            self.turn.status = str(
                payload.get("status") or interaction.get("status") or ""
            )
            if event_type == "interaction.completed":
                self.turn.usage = dict(interaction.get("usage") or {})
        elif event_type == "step.start" and step_type == "function_call":
            self._call_index = index if isinstance(index, int) else 0
            self._current_call = {
                "id": str(step.get("id", "")),
                "name": str(step.get("name", "")),
                "arguments": "",
            }
            if self._on_call:
                self._on_call({**self._current_call, "index": index})
        elif event_type == "step.delta":
            self._delta(delta, delta_type)
        elif event_type == "step.stop" and self._current_call is not None:
            self.turn.tool_calls.append(self._current_call)
            self._current_call = None
        elif event_type == "error":
            error = payload.get("error") or {}
            self.turn.errors.append(str(error.get("message", "unknown error")))

    def _delta(self, delta: Any, delta_type: str) -> None:
        if not isinstance(delta, dict):
            return
        if delta_type == "text":
            text = str(delta.get("text", ""))
            self.turn.on_content(text)
            if self._on_content:
                self._on_content(text)
        elif delta_type == "thought_summary":
            text = _text_from_content(delta.get("content"))
            self.turn.on_reasoning(text)
            if self._on_reasoning:
                self._on_reasoning(text)
        elif delta_type == "arguments_delta":
            if self._current_call is None:
                self._current_call = {"id": "", "name": "", "arguments": ""}
            self._current_call["arguments"] += str(delta.get("arguments", ""))
            if self._on_call:
                self._on_call(
                    {
                        **self._current_call,
                        "index": getattr(self, "_call_index", 0),
                        "arguments": str(delta.get("arguments", "")),
                    }
                )

    def result(self) -> NativeTurn:
        """Return the assembled turn, flushing a dangling function call."""
        if self._current_call is not None:
            self.turn.tool_calls.append(self._current_call)
            self._current_call = None
        return self.turn


def as_message(turn: NativeTurn) -> Any:
    """Return an OpenAI-shaped assistant message for the existing core loop."""
    calls = [
        SimpleNamespace(
            id=call["id"],
            type="function",
            function=SimpleNamespace(name=call["name"], arguments=call["arguments"]),
        )
        for call in turn.tool_calls
    ]
    return SimpleNamespace(role="assistant", content=turn.content, tool_calls=calls)
