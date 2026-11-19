"""Tests for streamed chunk accumulation."""

from __future__ import annotations

from types import SimpleNamespace

from magecode.core_loop import _assistant_message_dict
from magecode.utils.stream import consume_stream


def _chunk(delta=None, *, choices=True):
    if not choices:
        return SimpleNamespace(choices=[])
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def test_consume_empty_stream():
    message = consume_stream([])
    assert message.content == "" and message.tool_calls == []


def test_consume_skips_chunks_without_choices_or_delta():
    stream = [
        _chunk(choices=False),
        _chunk(None),
        _chunk(SimpleNamespace(content=None)),
    ]
    assert consume_stream(stream).content == ""


def test_consume_emits_content_deltas():
    seen = []
    stream = [
        _chunk(SimpleNamespace(content="Hel")),
        _chunk(SimpleNamespace(content="lo")),
        _chunk(SimpleNamespace(reasoning_content="ignored")),
    ]
    message = consume_stream(stream, on_delta=seen.append)
    assert message.content == "Hello"
    assert seen == ["Hel", "lo"]


def test_consume_accumulates_tool_call_and_signature():
    stream = [
        _chunk(
            SimpleNamespace(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id="call-1",
                        type="function",
                        function=SimpleNamespace(name="read_file", arguments='{"pa'),
                        extra_content={"google": {"thought_signature": "sig"}},
                    )
                ],
            )
        ),
        _chunk(
            SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id=None,
                        type=None,
                        function=SimpleNamespace(name=None, arguments='th":"x"}'),
                    )
                ]
            )
        ),
    ]
    message = consume_stream(stream)
    dumped = _assistant_message_dict(message)
    call = dumped["tool_calls"][0]
    assert call["id"] == "call-1"
    assert call["function"]["name"] == "read_file"
    assert call["function"]["arguments"] == '{"path":"x"}'
    assert call["extra_content"] == {"google": {"thought_signature": "sig"}}


def test_consume_multiple_tool_calls_without_index():
    stream = [
        _chunk(
            SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        index=None,
                        id="a",
                        type="function",
                        function=SimpleNamespace(name="one", arguments="{}"),
                    ),
                    SimpleNamespace(
                        index=None,
                        id="b",
                        type="function",
                        function=SimpleNamespace(name="two", arguments="{}"),
                    ),
                ]
            )
        )
    ]
    message = consume_stream(stream)
    assert [c.function.name for c in message.tool_calls] == ["one", "two"]


def test_consume_tool_call_without_optional_fields():
    stream = [
        _chunk(
            SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        index=None,
                        id=None,
                        type=None,
                        function=SimpleNamespace(name="", arguments=""),
                    )
                ]
            )
        )
    ]
    message = consume_stream(stream)
    assert message.tool_calls[0].id == ""


def test_consume_tool_call_without_function():
    stream = [
        _chunk(
            SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        index=0, id="call-x", type="function", function=None
                    )
                ]
            )
        )
    ]
    message = consume_stream(stream)
    assert message.tool_calls[0].function.name == ""
