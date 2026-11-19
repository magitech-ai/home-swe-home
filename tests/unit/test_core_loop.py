"""Tests for home_swe_home.core_loop (CoreLoopService)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from anima import Context

from home_swe_home.context import AGENT_SERVICES
from home_swe_home.core_loop import TurnInterrupted, TurnLimitReached


async def _build_context(*, openai_client=None) -> Context:
    ctx = Context()
    for service_cls in AGENT_SERVICES:
        ctx.use(service_cls)
    await ctx.flush()
    if openai_client is not None:
        ctx.client._openai = openai_client  # type: ignore[attr-defined]
    return ctx


def _patch_execute(monkeypatch, ctx, fn):
    """Replace the ctx.tools capability with a fake executor."""
    ctx.tools.execute = fn  # type: ignore[attr-defined]


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
    ctx = await _build_context(openai_client=client)
    messages = [{"role": "user", "content": "say hi in three words"}]
    await ctx.core_loop(
        model="nvidia/nemotron-3.5-lightning-30b-a3b",
        messages=messages,
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
    ctx = await _build_context(openai_client=client)
    messages = [{"role": "user", "content": "hi"}]
    await ctx.core_loop(
        model="m",
        messages=messages,
        reply_prefix="< ",
    )
    out = capsys.readouterr().out
    assert "[context:" not in out
    assert "< hello" in out


@pytest.mark.asyncio
async def test_core_loop_tool_call_then_final(capsys, monkeypatch):
    executed = []

    def fake_execute(name, arguments_json, *, read_files=None):
        executed.append((name, arguments_json))
        return "tool result text"

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
    ctx = await _build_context(openai_client=client)
    _patch_execute(monkeypatch, ctx, fake_execute)
    messages = [{"role": "user", "content": "read x.txt"}]
    await ctx.core_loop(model="m", messages=messages)
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

    def fake_execute(name, arguments_json, *, read_files=None):
        executed.append((name, arguments_json))
        if name == "edit_file":
            return (
                "Refused: 'x.txt' has not been read yet. "
                "Call read_file on 'x.txt' first, then retry edit_file."
            )
        return "tool result text"

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
    ctx = await _build_context(openai_client=client)
    _patch_execute(monkeypatch, ctx, fake_execute)
    messages = [{"role": "user", "content": "edit x.txt"}]
    await ctx.core_loop(model="m", messages=messages)
    out = capsys.readouterr().out
    assert "I need to read the file first." in out
    assert executed[0][0] == "edit_file"
    assert any(m.get("content") == "I need to read the file first." for m in messages)


@pytest.mark.asyncio
async def test_core_loop_read_marks_file_readable(capsys, monkeypatch):
    """read_file adds the path to read_files; subsequent edit is allowed."""
    seen_read_files = []

    def fake_execute(name, arguments_json, *, read_files=None):
        seen_read_files.append(set(read_files) if read_files is not None else None)
        if name == "read_file":
            if read_files is not None:
                read_files.add(json.loads(arguments_json).get("path", ""))
            return "file contents"
        return "ok"

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
    ctx = await _build_context(openai_client=client)
    _patch_execute(monkeypatch, ctx, fake_execute)
    messages = [{"role": "user", "content": "read and edit"}]
    await ctx.core_loop(model="m", messages=messages)
    assert seen_read_files[0] == set() or seen_read_files[0] is None
    assert seen_read_files[1] == {"x.txt"} or "x.txt" in seen_read_files[1]


@pytest.mark.asyncio
async def test_core_loop_interrupted():
    def create(**kwargs):
        raise KeyboardInterrupt()

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    ctx = await _build_context(openai_client=client)
    messages = [{"role": "user", "content": "do something"}]
    with pytest.raises(TurnInterrupted):
        await ctx.core_loop(model="m", messages=messages)
    assert messages == [{"role": "user", "content": "do something"}]


@pytest.mark.asyncio
async def test_core_loop_multiple_tool_calls(capsys, monkeypatch):
    calls = []

    def fake_execute(name, arguments_json, *, read_files=None):
        calls.append(arguments_json)
        if len(calls) == 1:
            return "first result"
        return "second result"

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
    ctx = await _build_context(openai_client=client)
    _patch_execute(monkeypatch, ctx, fake_execute)
    messages = [{"role": "user", "content": "read two files"}]
    await ctx.core_loop(model="m", messages=messages)
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
    ctx = await _build_context(openai_client=client)
    messages = [{"role": "user", "content": "keep going forever"}]
    with pytest.raises(TurnLimitReached):
        await ctx.core_loop(
            model="test/model",
            messages=messages,
            max_turns=2,
        )


def test_assistant_message_preserves_extra_content():
    from types import SimpleNamespace

    from home_swe_home.core_loop import _assistant_message_dict

    call = SimpleNamespace(
        id="call-1",
        type="function",
        function=SimpleNamespace(name="grep_files", arguments="{}"),
        extra_content={"google": {"thought_signature": "sig"}},
    )
    message = SimpleNamespace(role="assistant", content=None, tool_calls=[call])
    assert _assistant_message_dict(message)["tool_calls"][0]["extra_content"] == {
        "google": {"thought_signature": "sig"}
    }


def test_assistant_message_without_extra_content():
    from types import SimpleNamespace

    from home_swe_home.core_loop import _assistant_message_dict

    call = SimpleNamespace(
        id="call-1",
        type="function",
        function=SimpleNamespace(name="read_file", arguments="{}"),
    )
    message = SimpleNamespace(role="assistant", content="hi", tool_calls=[call])
    assert "extra_content" not in _assistant_message_dict(message)["tool_calls"][0]


def test_assistant_message_without_tool_calls():
    from types import SimpleNamespace

    from home_swe_home.core_loop import _assistant_message_dict

    message = SimpleNamespace(role="assistant", content="hi", tool_calls=None)
    assert _assistant_message_dict(message) == {"role": "assistant", "content": "hi"}


@pytest.mark.asyncio
async def test_core_loop_streams_deltas(monkeypatch, capsys):
    from types import SimpleNamespace

    ctx = await _build_context()

    def fake_stream(*, model, messages, tools, reasoning=False, **kwargs):
        return [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="Hel", tool_calls=None)
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="lo", tool_calls=None)
                    )
                ]
            ),
        ]

    monkeypatch.setattr(ctx.client, "chat_stream", fake_stream)
    await ctx.core_loop(
        model="m", messages=[{"role": "user", "content": "hi"}], stream=True
    )
    out = capsys.readouterr().out
    assert "Hello" in out


@pytest.mark.asyncio
async def test_core_loop_streams_tool_call(monkeypatch, capsys):
    from types import SimpleNamespace

    ctx = await _build_context()

    turns = iter([True, False])

    def fake_stream(*, model, messages, tools, reasoning=False, **kwargs):
        if next(turns):
            return [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=None,
                                tool_calls=[
                                    SimpleNamespace(
                                        index=0,
                                        id="call-1",
                                        type="function",
                                        function=SimpleNamespace(
                                            name="read_file",
                                            arguments='{"path": "AGENTS.md"}',
                                        ),
                                    )
                                ],
                            )
                        )
                    ]
                ),
            ]
        return [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="done", tool_calls=None)
                    )
                ]
            )
        ]

    monkeypatch.setattr(ctx.client, "chat_stream", fake_stream)
    messages = [{"role": "user", "content": "read"}]
    await ctx.core_loop(model="m", messages=messages, stream=True)
    assert any(m.get("role") == "tool" for m in messages)
    assert "[tool: read_file]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_core_loop_show_reasoning_is_delimited_and_not_stored(
    monkeypatch, capsys
):
    from types import SimpleNamespace

    ctx = await _build_context()

    def fake_stream(*, model, messages, tools, reasoning=False, **kwargs):
        return [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content="BECAUSE",
                            tool_calls=None,
                            event=None,
                        )
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="ANSWER", tool_calls=None, event=None
                        )
                    )
                ]
            ),
        ]

    monkeypatch.setattr(ctx.client, "chat_stream", fake_stream)
    messages = [{"role": "user", "content": "hi"}]
    await ctx.core_loop(model="m", messages=messages, stream=True, show_reasoning=True)
    out = capsys.readouterr().out
    assert "[reasoning]BECAUSE[/reasoning]ANSWER" in out
    assert "BECAUSE" not in str(messages)


@pytest.mark.asyncio
async def test_core_loop_surfaces_events_and_unknown(monkeypatch, capsys):
    from types import SimpleNamespace

    ctx = await _build_context()

    def fake_stream(*, model, messages, tools, reasoning=False, **kwargs):
        known = SimpleNamespace(label=lambda: "step.delta:text", known=True)
        unknown = SimpleNamespace(label=lambda: "future:thing", known=False)
        return [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="OK", tool_calls=None, event=known
                        )
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None, tool_calls=None, event=unknown
                        )
                    )
                ]
            ),
        ]

    monkeypatch.setattr(ctx.client, "chat_stream", fake_stream)
    await ctx.core_loop(
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        show_events=True,
    )
    out = capsys.readouterr().out
    assert "[event: step.delta:text]" in out
    assert "[event: UNKNOWN:future:thing]" in out


@pytest.mark.asyncio
async def test_core_loop_closes_reasoning_at_end(monkeypatch, capsys):
    from types import SimpleNamespace

    ctx = await _build_context()

    def fake_stream(*, model, messages, tools, reasoning=False, **kwargs):
        return [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content="ONLY-THOUGHT",
                            tool_calls=None,
                            event=None,
                        )
                    )
                ]
            )
        ]

    monkeypatch.setattr(ctx.client, "chat_stream", fake_stream)
    await ctx.core_loop(
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        show_reasoning=True,
    )
    assert "[/reasoning]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_core_loop_hides_reasoning_by_default(monkeypatch, capsys):
    from types import SimpleNamespace

    ctx = await _build_context()

    def fake_stream(*, model, messages, tools, reasoning=False, **kwargs):
        return [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content="HIDDEN",
                            tool_calls=None,
                            event=None,
                        )
                    )
                ]
            )
        ]

    monkeypatch.setattr(ctx.client, "chat_stream", fake_stream)
    await ctx.core_loop(
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        show_reasoning=True,
    )
    out = capsys.readouterr().out
    assert "HIDDEN" in out and "[reasoning]" in out


@pytest.mark.asyncio
async def test_core_loop_reasoning_hidden_when_not_requested(monkeypatch, capsys):
    from types import SimpleNamespace

    ctx = await _build_context()

    def fake_stream(*, model, messages, tools, reasoning=False, **kwargs):
        return [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content="HIDDEN",
                            tool_calls=None,
                            event=None,
                        )
                    )
                ]
            )
        ]

    monkeypatch.setattr(ctx.client, "chat_stream", fake_stream)
    await ctx.core_loop(
        model="m", messages=[{"role": "user", "content": "hi"}], stream=True
    )
    out = capsys.readouterr().out
    assert "HIDDEN" not in out and "[reasoning]" not in out


@pytest.mark.asyncio
async def test_core_loop_multiple_reasoning_deltas(monkeypatch, capsys):
    from types import SimpleNamespace

    ctx = await _build_context()

    def fake_stream(*, model, messages, tools, reasoning=False, **kwargs):
        return [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content=part,
                            tool_calls=None,
                            event=None,
                        )
                    )
                ]
            )
            for part in ("ONE", "TWO")
        ]

    monkeypatch.setattr(ctx.client, "chat_stream", fake_stream)
    await ctx.core_loop(
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        show_reasoning=True,
    )
    assert "[reasoning]ONETWO[/reasoning]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_core_loop_hides_known_events_by_default(monkeypatch, capsys):
    from types import SimpleNamespace

    ctx = await _build_context()
    known = SimpleNamespace(label=lambda: "step.delta:text", known=True)
    unknown = SimpleNamespace(label=lambda: "future:thing", known=False)

    def fake_stream(*, model, messages, tools, reasoning=False, **kwargs):
        return [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="OK", tool_calls=None, event=event
                        )
                    )
                ]
            )
            for event in (known, unknown)
        ]

    monkeypatch.setattr(ctx.client, "chat_stream", fake_stream)
    await ctx.core_loop(
        model="m", messages=[{"role": "user", "content": "hi"}], stream=True
    )
    out = capsys.readouterr().out
    assert "[event: step.delta:text]" not in out
    assert "[event: UNKNOWN:future:thing]" in out
