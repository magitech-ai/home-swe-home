"""Tests for full Gemini Interactions event translation."""

from __future__ import annotations

from types import SimpleNamespace

from magecode.utils.native_events import (
    DELTA_TYPES,
    EVENT_TYPES,
    NativeEvent,
    NativeTranslator,
    as_dict,
    as_message,
)


def test_all_reference_types_are_declared():
    assert len(EVENT_TYPES) == 8
    assert len(DELTA_TYPES) == 24


def test_as_dict_accepts_objects_without_model_dump():
    assert as_dict(SimpleNamespace(event_type="done")) == {"event_type": "done"}


def test_plain_text_stream():
    t = NativeTranslator()
    t.feed({"event_type": "interaction.created", "interaction": {"id": "i1"}})
    t.feed({"event_type": "step.start", "index": 0, "step": {"type": "model_output"}})
    t.feed(
        {
            "event_type": "step.delta",
            "index": 0,
            "delta": {"type": "text", "text": "Hi"},
        }
    )
    t.feed({"event_type": "step.stop", "index": 0})
    t.feed(
        {
            "event_type": "interaction.completed",
            "interaction": {"status": "completed", "usage": {"total_tokens": 5}},
        }
    )
    turn = t.result()
    assert turn.interaction_id == "i1"
    assert turn.content == "Hi"
    assert turn.status == "completed"
    assert turn.usage == {"total_tokens": 5}
    assert turn.unknown == ()
    assert all(e.known for e in turn.events)


def test_reasoning_and_signature():
    t = NativeTranslator()
    t.feed({"event_type": "step.start", "index": 0, "step": {"type": "thought"}})
    t.feed(
        {
            "event_type": "step.delta",
            "index": 0,
            "delta": {
                "type": "thought_summary",
                "content": {"type": "text", "text": "Think"},
            },
        }
    )
    t.feed(
        {
            "event_type": "step.delta",
            "index": 0,
            "delta": {"type": "thought_signature", "signature": "sig"},
        }
    )
    turn = t.result()
    assert turn.reasoning == "Think"
    assert any(e.delta_type == "thought_signature" for e in turn.events)


def test_function_call_accumulation_and_flush():
    t = NativeTranslator()
    t.feed(
        {
            "event_type": "step.start",
            "index": 1,
            "step": {"type": "function_call", "id": "c1", "name": "echo"},
        }
    )
    t.feed(
        {
            "event_type": "step.delta",
            "index": 1,
            "delta": {"type": "arguments_delta", "arguments": '{"x":'},
        }
    )
    t.feed(
        {
            "event_type": "step.delta",
            "index": 1,
            "delta": {"type": "arguments_delta", "arguments": "1}"},
        }
    )
    turn = t.result()  # no step.stop: flushed in result()
    assert turn.tool_calls == [{"id": "c1", "name": "echo", "arguments": '{"x":1}'}]
    message = as_message(turn)
    assert message.tool_calls[0].function.name == "echo"


def test_function_call_with_step_stop():
    t = NativeTranslator()
    t.feed(
        {
            "event_type": "step.start",
            "index": 0,
            "step": {"type": "function_call", "id": "c2", "name": "run"},
        }
    )
    t.feed(
        {
            "event_type": "step.delta",
            "index": 0,
            "delta": {"type": "arguments_delta", "arguments": "{}"},
        }
    )
    t.feed({"event_type": "step.stop", "index": 0})
    assert t.result().tool_calls[0]["id"] == "c2"


def test_arguments_delta_without_prior_call():
    t = NativeTranslator()
    t.feed(
        {
            "event_type": "step.delta",
            "index": 2,
            "delta": {"type": "arguments_delta", "arguments": "{}"},
        }
    )
    assert t.result().tool_calls == [{"id": "", "name": "", "arguments": "{}"}]


def test_error_and_unknown_events_are_surfaced():
    t = NativeTranslator()
    t.feed({"event_type": "error", "error": {"message": "boom", "code": "x"}})
    t.feed(
        {
            "event_type": "interaction.status_update",
            "interaction_id": "i",
            "status": "in_progress",
        }
    )
    t.feed({"event_type": "done"})
    t.feed({"event_type": "future.event", "step": {"type": "mystery"}})
    turn = t.result()
    assert turn.errors == ["boom"]
    assert turn.status == "in_progress"
    assert "future.event:mystery" in turn.unknown


def test_every_known_delta_type_is_recorded():
    payloads = {
        "arguments_delta": {"arguments": "{}"},
        "audio": {"data": "AAAA", "mime_type": "audio/wav"},
        "code_execution_call": {"arguments": {"code": "1+1"}},
        "code_execution_result": {"result": "2"},
        "document": {"data": "doc"},
        "file_search_call": {"signature": "s"},
        "file_search_result": {"result": []},
        "function_result": {"result": {"content": []}},
        "google_maps_call": {"arguments": {}},
        "google_maps_result": {"result": []},
        "google_search_call": {"arguments": {"queries": ["x"]}},
        "google_search_result": {"result": []},
        "image": {"data": "img", "mime_type": "image/png"},
        "mcp_server_tool_call": {"name": "t", "server_name": "s", "arguments": {}},
        "mcp_server_tool_result": {"result": "ok"},
        "processing_call": {"signature": "s"},
        "processing_result": {"signature": "s"},
        "text_annotation_delta": {"annotations": []},
        "thought_signature": {"signature": "sig"},
        "thought_summary": {"content": ["text"]},
        "url_context_call": {"arguments": {"urls": ["x"]}},
        "url_context_result": {"result": []},
        "video": {"data": "vid", "mime_type": "video/mp4"},
    }
    t = NativeTranslator()
    for kind, body in payloads.items():
        t.feed(
            {"event_type": "step.delta", "index": 0, "delta": {"type": kind, **body}}
        )
    turn = t.result()
    assert {e.delta_type for e in turn.events} == DELTA_TYPES - {"text"}
    assert turn.unknown == ()


def test_unknown_delta_type_flagged():
    t = NativeTranslator()
    t.feed(
        {"event_type": "step.delta", "index": 0, "delta": {"type": "brand_new", "x": 1}}
    )
    assert "step.delta:brand_new" in t.result().unknown


def test_text_from_content_variants():
    from magecode.utils.native_events import _text_from_content

    assert _text_from_content("a") == "a"
    assert _text_from_content({"type": "text", "text": "b"}) == "b"
    assert _text_from_content({"type": "image", "data": "x"}) == ""
    assert _text_from_content([{"type": "text", "text": "c"}]) == "c"
    assert _text_from_content(7) == ""


def test_live_hooks_receive_values():
    content, reasoning, events, ids, calls = [], [], [], [], []
    t = NativeTranslator(
        on_content=content.append,
        on_reasoning=reasoning.append,
        on_event=events.append,
        on_interaction=ids.append,
        on_call=calls.append,
    )
    t.feed({"event_type": "interaction.created", "interaction": {"id": "i7"}})
    t.feed(
        {"event_type": "step.delta", "index": 0, "delta": {"type": "text", "text": "T"}}
    )
    t.feed(
        {
            "event_type": "step.delta",
            "index": 0,
            "delta": {
                "type": "thought_summary",
                "content": {"type": "text", "text": "R"},
            },
        }
    )
    t.feed(
        {
            "event_type": "step.start",
            "index": 1,
            "step": {"type": "function_call", "id": "c", "name": "n"},
        }
    )
    t.feed(
        {
            "event_type": "step.delta",
            "index": 1,
            "delta": {"type": "arguments_delta", "arguments": "{}"},
        }
    )
    assert content == ["T"] and reasoning == ["R"] and ids == ["i7"]
    assert len(calls) == 2 and len(events) == 5


def test_native_event_label_without_types():
    event = NativeEvent("interaction.created", True)
    assert event.label() == "interaction.created"


def test_as_dict_with_model_dump_object():
    class Event:
        def model_dump(self, **kwargs):
            return {"event_type": "done"}

    assert as_dict(Event()) == {"event_type": "done"}


def test_summary_of_non_dict_payload():
    from magecode.utils.native_events import _summary

    assert _summary("plain") == {"value": "plain"}


def test_non_dict_delta_is_ignored():
    t = NativeTranslator()
    t.feed({"event_type": "step.delta", "index": 0, "delta": "not a dict"})
    assert t.result().content == ""
