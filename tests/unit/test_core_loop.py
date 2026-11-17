"""Tests for magecode.core_loop (CoreLoopService)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from anima import Context

from magecode.core_loop import (
    CoreLoopService,
    TurnInterrupted,
    TurnLimitReached,
)
from magecode.tools import (
    CodeMetricsService,
    DeleteFileService,
    EditFileService,
    FindDuplicatesService,
    GenerateDocsService,
    GrepFilesService,
    ListDirectoryService,
    ReadFileService,
    ReloadModuleService,
    RunCommandService,
    WebSearchService,
    WriteFileService,
)

TOOL_SERVICES = [
    ReadFileService,
    WriteFileService,
    EditFileService,
    DeleteFileService,
    ListDirectoryService,
    GrepFilesService,
    RunCommandService,
    WebSearchService,
    ReloadModuleService,
    CodeMetricsService,
    FindDuplicatesService,
    GenerateDocsService,
    CoreLoopService,
]


async def _build_context() -> Context:
    ctx = Context()
    for service_cls in TOOL_SERVICES:
        ctx.use(service_cls)
    await ctx.flush()
    return ctx


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


@pytest.mark.asyncio
async def test_core_loop_final_text(capsys):
    message = assistant_message("hi there friend")
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create(message)))
    )
    ctx = await _build_context()
    messages = [{"role": "user", "content": "say hi in three words"}]
    await ctx.core_loop(
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


@pytest.mark.asyncio
async def test_core_loop_chat_mode_no_context_print(capsys):
    """Chat mode (reply_prefix set) does not print the context token count."""
    message = assistant_message("hello")
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create(message)))
    )
    ctx = await _build_context()
    messages = [{"role": "user", "content": "hi"}]
    await ctx.core_loop(
        model="m",
        messages=messages,
        client=client,
        reply_prefix="< ",
    )
    out = capsys.readouterr().out
    assert "[context:" not in out
    assert "< hello" in out


@pytest.mark.asyncio
async def test_core_loop_tool_call_then_final(capsys, monkeypatch):
    executed = []

    def fake_execute(ctx, name, arguments_json, *, read_files=None):
        executed.append((name, arguments_json))
        return "tool result text"

    monkeypatch.setattr("magecode.core_loop.execute_tool", fake_execute)
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
    ctx = await _build_context()
    messages = [{"role": "user", "content": "read x.txt"}]
    await ctx.core_loop(model="m", messages=messages, client=client)
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


@pytest.mark.asyncio
async def test_core_loop_edit_refused_when_unread(capsys, monkeypatch):
    """edit_file on an unread path returns a refusal; turn continues."""
    executed = []

    def fake_execute(ctx, name, arguments_json, *, read_files=None):
        executed.append((name, arguments_json))
        if name == "edit_file":
            return (
                "Refused: 'x.txt' has not been read yet. "
                "Call read_file on 'x.txt' first, then retry edit_file."
            )
        return "tool result text"

    monkeypatch.setattr("magecode.core_loop.execute_tool", fake_execute)
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
    ctx = await _build_context()
    messages = [{"role": "user", "content": "edit x.txt"}]
    await ctx.core_loop(model="m", messages=messages, client=client)
    out = capsys.readouterr().out
    assert "I need to read the file first." in out
    assert executed[0][0] == "edit_file"
    assert any(m.get("content") == "I need to read the file first." for m in messages)


@pytest.mark.asyncio
async def test_core_loop_read_marks_file_readable(capsys, monkeypatch):
    """read_file adds the path to read_files; subsequent edit is allowed."""
    seen_read_files = []

    def fake_execute(ctx, name, arguments_json, *, read_files=None):
        seen_read_files.append(set(read_files) if read_files is not None else None)
        if name == "read_file":
            if read_files is not None:
                read_files.add(json.loads(arguments_json).get("path", ""))
            return "file contents"
        return "ok"

    monkeypatch.setattr("magecode.core_loop.execute_tool", fake_execute)
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
    ctx = await _build_context()
    messages = [{"role": "user", "content": "read and edit"}]
    await ctx.core_loop(model="m", messages=messages, client=client)
    assert seen_read_files[0] == set() or seen_read_files[0] is None
    assert seen_read_files[1] == {"x.txt"} or "x.txt" in seen_read_files[1]


@pytest.mark.asyncio
async def test_core_loop_interrupted():
    def create(**kwargs):
        raise KeyboardInterrupt()

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    ctx = await _build_context()
    messages = [{"role": "user", "content": "do something"}]
    with pytest.raises(TurnInterrupted):
        await ctx.core_loop(model="m", messages=messages, client=client)
    assert messages == [{"role": "user", "content": "do something"}]


@pytest.mark.asyncio
async def test_core_loop_multiple_tool_calls(capsys, monkeypatch):
    calls = []

    def fake_execute(ctx, name, arguments_json, *, read_files=None):
        calls.append(arguments_json)
        if len(calls) == 1:
            return "first result"
        return "second result"

    monkeypatch.setattr("magecode.core_loop.execute_tool", fake_execute)
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
    ctx = await _build_context()
    messages = [{"role": "user", "content": "read two files"}]
    await ctx.core_loop(model="m", messages=messages, client=client)
    assert calls == ['{"path": "a.txt"}', '{"path": "b.txt"}']
    assert any(message.get("content") == "combined" for message in messages)


@pytest.mark.asyncio
async def test_core_loop_turn_limit_reached():
    """CoreLoopService should raise TurnLimitReached when max_turns exceeded."""

    def create(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        role="assistant",
                        content="I'll keep going",
                        tool_calls=[
                            SimpleNamespace(
                                id="call-1",
                                type="function",
                                function=SimpleNamespace(
                                    name="read_file", arguments='{"path": "x.txt"}'
                                ),
                            )
                        ],
                    )
                )
            ],
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    ctx = await _build_context()
    messages = [{"role": "user", "content": "keep going forever"}]
    with pytest.raises(TurnLimitReached):
        await ctx.core_loop(
            model="test/model",
            messages=messages,
            client=client,
            max_turns=2,
        )
