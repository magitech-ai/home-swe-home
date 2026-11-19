"""Tests for the native Interactions client adapter."""

from __future__ import annotations

from magecode.native import native_input, native_stream, native_tools


def test_native_tools_conversion():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo",
                "parameters": {"type": "object"},
            },
        }
    ]
    assert native_tools(tools) == [
        {
            "type": "function",
            "name": "echo",
            "description": "Echo",
            "parameters": {"type": "object"},
        }
    ]
    assert native_tools(None) == []


def test_native_input_initial_call_includes_system_and_user():
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]
    current, results = native_input(messages, has_interaction=False)
    assert current == [
        {"type": "text", "text": "SYS"},
        {"type": "text", "text": "USER"},
    ]
    assert results == []


def test_native_input_tool_results_when_stateful():
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "do it"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "function": {"name": "echo"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "DONE"},
    ]
    current, results = native_input(messages, has_interaction=True)
    assert current[0]["type"] == "function_result"
    assert current[0]["call_id"] == "c1"
    assert current[0]["result"]["content"][0]["text"] == "DONE"
    assert results == current


def test_native_input_tool_results_without_state_falls_back_to_user():
    messages = [
        {"role": "user", "content": "do it"},
        {"role": "tool", "tool_call_id": "c1", "content": "DONE"},
    ]
    current, _ = native_input(messages, has_interaction=False)
    assert current == [{"type": "text", "text": "do it"}]


def test_native_stream_translates_all_event_kinds():
    from types import SimpleNamespace

    events = [
        {"event_type": "interaction.created", "interaction": {"id": "i1"}},
        {"event_type": "interaction.status_update", "status": "in_progress"},
        {"event_type": "step.start", "index": 0, "step": {"type": "thought"}},
        {
            "event_type": "step.delta",
            "index": 0,
            "delta": {
                "type": "thought_summary",
                "content": {"type": "text", "text": "THINK"},
            },
        },
        {
            "event_type": "step.delta",
            "index": 0,
            "delta": {"type": "thought_signature", "signature": "sig"},
        },
        {"event_type": "step.stop", "index": 0},
        {
            "event_type": "step.start",
            "index": 1,
            "step": {"type": "function_call", "id": "c1", "name": "echo"},
        },
        {
            "event_type": "step.delta",
            "index": 1,
            "delta": {"type": "arguments_delta", "arguments": '{"x":1}'},
        },
        {"event_type": "step.stop", "index": 1},
        {"event_type": "step.start", "index": 2, "step": {"type": "model_output"}},
        {
            "event_type": "step.delta",
            "index": 2,
            "delta": {"type": "text", "text": "FINAL"},
        },
        {"event_type": "step.stop", "index": 2},
        {
            "event_type": "interaction.completed",
            "interaction": {"status": "requires_action", "usage": {"total_tokens": 3}},
        },
        {"event_type": "error", "error": {"message": "oops"}},
        {"event_type": "future.unknown", "step": {"type": "mystery"}},
        {"event_type": "done"},
    ]

    class FakeInteractions:
        def create(self, **params):
            self.params = params
            return events

    fake = SimpleNamespace(interactions=FakeInteractions())
    ids: list[str] = []
    chunks = list(
        native_stream(
            fake,
            model="gemini-4-neon",
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            reasoning=True,
            interaction_id=None,
            on_interaction=ids.append,
        )
    )
    assert ids == ["i1"]
    deltas = [c.choices[0].delta for c in chunks]
    assert any(d.content == "FINAL" for d in deltas)
    assert any(d.reasoning_content == "THINK" for d in deltas)
    assert any(
        d.tool_calls and d.tool_calls[0].function.arguments == '{"x":1}' for d in deltas
    )
    assert any(d.event is not None and not d.event.known for d in deltas)
    assert fake.interactions.params["generation_config"] == {
        "thinking_level": "medium",
        "thinking_summaries": "auto",
    }
    assert fake.interactions.params["store"] is True
    assert "previous_interaction_id" not in fake.interactions.params


def test_native_stream_stateful_and_no_reasoning():
    from types import SimpleNamespace

    class FakeInteractions:
        def create(self, **params):
            self.params = params
            return [{"event_type": "done"}]

    fake = SimpleNamespace(interactions=FakeInteractions())
    list(
        native_stream(
            fake,
            model="gemini-4-neon",
            messages=[{"role": "tool", "tool_call_id": "c1", "content": "DONE"}],
            tools=None,
            reasoning=False,
            interaction_id="prev",
            on_interaction=lambda _id: None,
        )
    )
    assert fake.interactions.params["previous_interaction_id"] == "prev"
    assert fake.interactions.params["generation_config"] == {"thinking_level": "medium"}


def test_native_input_stateful_without_user_message():
    current, results = native_input(
        [{"role": "system", "content": "SYS"}], has_interaction=True
    )
    assert current == [] and results == []
