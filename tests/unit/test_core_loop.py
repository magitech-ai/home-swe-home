"""Tests for mini_claude.core_loop."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from mini_claude.core_loop import (
    TurnInterrupted,
    run_core_loop,
)


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


def test_run_core_loop_final_text(capsys):
    message = assistant_message("hi there friend")
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create(message)))
    )
    messages = [{"role": "user", "content": "say hi in three words"}]
    run_core_loop(
        model="nvidia/nemotron-3.5-lightning-30b-a3b",
        messages=messages,
        client=client,
    )
    out = capsys.readouterr().out
    assert out.endswith("hi there friend\n")
    assert "[context:" in out
    assert messages == [
        {"role": "user", "content": "say hi in three words"},
        {"role": "assistant", "content": "hi there friend"},
    ]


def test_run_core_loop_tool_call_then_final(capsys, monkeypatch):
    executed = []

    def fake_execute(name, arguments_json, *, read_files=None):
        executed.append((name, arguments_json))
        return "tool result text"

    monkeypatch.setattr("mini_claude.core_loop.execute_tool", fake_execute)
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
    run_core_loop(model="m", messages=messages, client=client)
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


def test_run_core_loop_edit_refused_when_unread(capsys, monkeypatch):
    """edit_file on an unread path returns a refusal; turn continues."""
    executed = []

    def fake_execute(name, arguments_json, *, read_files=None):
        executed.append((name, arguments_json))
        if name == "edit_file":
            return (
                "Refused: 'x.txt' has not been read yet. "
                "Call read_file on 'x.txt' first, then retry edit_file."
            )
        return "tool result text"

    monkeypatch.setattr("mini_claude.core_loop.execute_tool", fake_execute)
    edit_args = '{"path": "x.txt", "old_string": "a", "new_string": "b"}'
    first = assistant_message(
        None,
        [tool_call("call-1", "edit_file", edit_args)],
    )
    second = assistant_message("I need to read the file first.")
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create(first, second))
        )
    )
    messages = [{"role": "user", "content": "edit x.txt"}]
    run_core_loop(model="m", messages=messages, client=client)
    out = capsys.readouterr().out
    assert "I need to read the file first." in out
    # The edit call was made and the refusal fed back; the model replied after.
    assert executed[0][0] == "edit_file"
    assert any(m.get("content") == "I need to read the file first." for m in messages)


def test_run_core_loop_read_marks_file_readable(capsys, monkeypatch):
    """read_file adds the path to read_files; subsequent edit is allowed."""
    seen_read_files = []

    def fake_execute(name, arguments_json, *, read_files=None):
        seen_read_files.append(set(read_files) if read_files is not None else None)
        if name == "read_file":
            if read_files is not None:
                read_files.add(json.loads(arguments_json).get("path", ""))
            return "file contents"
        return "ok"

    monkeypatch.setattr("mini_claude.core_loop.execute_tool", fake_execute)
    edit_args = '{"path": "x.txt", "old_string": "a", "new_string": "b"}'
    first = assistant_message(None, [tool_call("c1", "read_file", '{"path": "x.txt"}')])
    second = assistant_message(
        None,
        [tool_call("c2", "edit_file", edit_args)],
    )
    third = assistant_message("done")
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create(first, second, third))
        )
    )
    messages = [{"role": "user", "content": "read and edit"}]
    run_core_loop(model="m", messages=messages, client=client)
    # Before read_file: read_files is empty. After read_file: x.txt is in it.
    assert seen_read_files[0] == set() or seen_read_files[0] is None
    assert seen_read_files[1] == {"x.txt"} or "x.txt" in seen_read_files[1]


def test_run_core_loop_interrupted():
    def create(**kwargs):
        raise KeyboardInterrupt()

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    messages = [{"role": "user", "content": "do something"}]
    with pytest.raises(TurnInterrupted):
        run_core_loop(model="m", messages=messages, client=client)
    assert messages == [{"role": "user", "content": "do something"}]


def test_run_turn_multiple_tool_calls(capsys, monkeypatch):
    calls = []

    def fake_execute(name, arguments_json, *, read_files=None):
        calls.append(arguments_json)
        if len(calls) == 1:
            return "first result"
        return "second result"

    monkeypatch.setattr("mini_claude.core_loop.execute_tool", fake_execute)
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
    run_core_loop(model="m", messages=messages, client=client)
    assert calls == ['{"path": "a.txt"}', '{"path": "b.txt"}']
    assert any(message.get("content") == "combined" for message in messages)
