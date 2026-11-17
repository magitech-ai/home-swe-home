"""Tests for mini_claude.turn."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mini_claude.turn import TurnInterrupted, run_turn


def assistant_message(content=None, tool_calls=None):
    return SimpleNamespace(role="assistant", content=content, tool_calls=tool_calls)


def tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def fake_response(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def fake_create(*responses):
    responses = [fake_response(message) for message in responses]

    def create(**kwargs):
        return responses.pop(0)

    return create


def test_run_turn_final_text(capsys):
    message = assistant_message("hi there friend")
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create(message)))
    )
    messages = [{"role": "user", "content": "say hi in three words"}]
    run_turn(
        model="nvidia/nemotron-3.5-lightning-30b-a3b", messages=messages, client=client
    )
    out = capsys.readouterr().out
    assert out == "hi there friend\n"
    assert messages == [
        {"role": "user", "content": "say hi in three words"},
        {"role": "assistant", "content": "hi there friend"},
    ]


def test_run_turn_reply_prefix(capsys):
    message = assistant_message("hi there friend")
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create(message)))
    )
    messages = [{"role": "user", "content": "say hi in three words"}]
    run_turn(
        model="nvidia/nemotron-3.5-lightning-30b-a3b",
        messages=messages,
        client=client,
        reply_prefix="< ",
    )
    out = capsys.readouterr().out
    assert out == "< hi there friend\n"


def test_run_turn_tool_call_then_final(capsys, monkeypatch):
    executed = []

    def fake_execute(name, arguments_json):
        executed.append((name, arguments_json))
        return "tool result text"

    monkeypatch.setattr("mini_claude.turn.execute_tool", fake_execute)
    first = assistant_message(
        None, [tool_call("call-1", "read_file", '{"path": "x.txt"}')]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=fake_create(first, assistant_message("all done"))
            )
        )
    )
    messages = [{"role": "user", "content": "read x.txt"}]
    run_turn(model="m", messages=messages, client=client)
    out = capsys.readouterr().out
    assert "all done" in out
    assert executed == [("read_file", '{"path": "x.txt"}')]
    assert messages == [
        {"role": "user", "content": "read x.txt"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "x.txt"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "tool result text"},
        {"role": "assistant", "content": "all done"},
    ]


def test_run_turn_interrupted():
    def create(**kwargs):
        raise KeyboardInterrupt()

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    messages = [{"role": "user", "content": "do something"}]
    with pytest.raises(TurnInterrupted):
        run_turn(model="m", messages=messages, client=client)
    assert messages == [{"role": "user", "content": "do something"}]


def test_run_turn_multiple_tool_calls(capsys, monkeypatch):
    calls = []

    def fake_execute(name, arguments_json):
        calls.append(arguments_json)
        if len(calls) == 1:
            return "first result"
        return "second result"

    monkeypatch.setattr("mini_claude.turn.execute_tool", fake_execute)
    first = assistant_message(None, [tool_call("c1", "read_file", '{"path": "a.txt"}')])
    second = assistant_message(
        None, [tool_call("c2", "read_file", '{"path": "b.txt"}')]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=fake_create(first, second, assistant_message("combined"))
            )
        )
    )
    messages = [{"role": "user", "content": "read two files"}]
    run_turn(model="m", messages=messages, client=client)
    assert calls == ['{"path": "a.txt"}', '{"path": "b.txt"}']
    assert any(message.get("content") == "combined" for message in messages)
