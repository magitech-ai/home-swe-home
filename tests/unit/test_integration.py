"""Integration tests for home-swe-home on magitech-harness.

Exercises the full stack: context assembly, tool registration, agent creation,
tool execution through mth's pipeline, and session logging.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from magitech_harness.llm.message import create_user_message


def _make_mock_adapter(script: list[list[dict[str, Any]]]) -> MagicMock:
    """Build a mock LLM adapter that yields scripted stream chunks per call."""
    call_count = 0

    async def _stream(options: Any) -> Any:
        nonlocal call_count
        chunks = script[call_count] if call_count < len(script) else script[-1]
        call_count += 1
        for chunk in chunks:
            yield chunk

    adapter = MagicMock()
    adapter.provider_info.return_value = {"id": "mock", "name": "Mock"}
    adapter.list_models = AsyncMock(return_value=[])
    adapter.resolve_model = AsyncMock(
        return_value={
            "provider": "mock",
            "id": "mock-1",
            "name": "Mock 1",
            "reasoning": {
                "efforts": [{"id": "medium", "name": "Medium"}],
                "defaultEffort": "medium",
            },
        }
    )
    adapter.prepare_call = AsyncMock(
        return_value=MagicMock(
            model={"provider": "mock", "id": "mock-1", "name": "Mock 1"},
            stream=lambda opts: _stream(opts),
        )
    )
    return adapter


@pytest.mark.asyncio
async def test_full_stack_read_file(tmp_path: Any) -> None:
    """Create a file, then have the agent read it via a tool call."""
    from home_swe_home.context import build_context

    # Create a test file.
    test_file = tmp_path / "hello.txt"
    test_file.write_text("Hello, world!", encoding="utf-8")

    # Script: first call returns a tool call, second returns text.
    script = [
        [
            {"type": "block-start", "index": 0, "blockType": "tool-call"},
            {
                "type": "tool-call-delta",
                "index": 0,
                "id": "call_1",
                "name": "read_file",
                "argumentsDelta": json.dumps({"path": str(test_file)}),
            },
            {
                "type": "block-end",
                "index": 0,
                "block": {
                    "type": "tool-call",
                    "id": "call_1",
                    "name": "read_file",
                    "arguments": json.dumps({"path": str(test_file)}),
                },
            },
            {"type": "finish", "reason": {"kind": "tool-calls"}},
        ],
        [
            {"type": "block-start", "index": 0, "blockType": "text"},
            {"type": "text-delta", "index": 0, "text": "The file says: Hello, world!"},
            {
                "type": "block-end",
                "index": 0,
                "block": {"type": "text", "text": "The file says: Hello, world!"},
            },
            {"type": "finish", "reason": {"kind": "stop"}},
        ],
    ]

    ctx = await build_context(storage_dir=tmp_path)
    ctx.llm.register_adapter(["mock"], _make_mock_adapter(script))

    handle = await ctx.agents.create(
        {
            "sessionId": "read-test",
            "agentOptions": {"provider": "mock", "model": "mock-1"},
        }
    )
    agent = handle["agent"]

    agent.followup(
        create_user_message(
            content=[{"type": "text", "text": f"Read {test_file}"}],
            source={"kind": "user"},
        )
    )
    await agent.when_idle()

    # Verify the session log has the tool call and result.
    from magitech_harness import EventType

    event_types = [e.type for e in agent.session.events]
    assert EventType.TOOL_CALL in event_types, "No tool/call event"
    assert EventType.TOOL_RESULT in event_types, "No tool/result event"
    assert EventType.ASSISTANT_MESSAGE in event_types, "No assistant/message"

    # Verify the tool result contains the file contents.
    tool_results = [e for e in agent.session.events if e.type == EventType.TOOL_RESULT]
    assert len(tool_results) == 1
    result_content = tool_results[0].payload.get("message", {}).get("content", [])
    result_text = ""
    for block in result_content:
        if isinstance(block, dict) and block.get("type") == "text":
            result_text += block.get("text", "")
    assert "Hello, world!" in result_text, f"File content not in result: {result_text}"

    await handle["dispose"]()


@pytest.mark.asyncio
async def test_tool_definitions_registered(tmp_path: Any) -> None:
    """All mth-mounted tools are registered on the context."""
    from home_swe_home.context import build_context

    ctx = await build_context(storage_dir=tmp_path)
    defs = ctx.tools.definitions()
    names = {d["name"] for d in defs}
    expected = {
        "add_repo",
        "bash",
        "code_metrics",
        "delete_file",
        "edit_file",
        "find_duplicates",
        "generate_docs",
        "glob",
        "grep",
        "list_directory",
        "okf_bundle",
        "read_file",
        "reload_module",
        "skill",
        "verify_repo",
        "web_search",
        "write_file",
    }
    assert names == expected, f"Tool mismatch: {names} != {expected}"
    schema_names = {s["name"] for s in ctx.tools.schemas()}
    assert expected <= schema_names
    assert schema_names == names


@pytest.mark.asyncio
async def test_mounted_read_file_pagination(tmp_path: Any) -> None:
    """The mth read_file tool returns only the requested line window."""
    from magitech_harness.session.events import ToolCallData

    from home_swe_home.context import build_context

    f = tmp_path / "lines.txt"
    f.write_text("\n".join(f"line-{i}" for i in range(1, 11)), encoding="utf-8")
    ctx = await build_context(storage_dir=tmp_path / "sessions")

    result = await ctx.tools.execute(
        ToolCallData(
            call_id="paginated",
            name="read_file",
            arguments={"path": str(f), "offset": 3, "limit": 2},
        )
    )
    assert result.content == "line-3\nline-4"
    assert "line-1" not in result.content
    assert "line-5" not in result.content


@pytest.mark.asyncio
async def test_mounted_truncation_guard_caps_large_read(tmp_path: Any) -> None:
    """The mounted truncation guard caps oversized tool output."""
    from magitech_harness.session.events import ToolCallData

    from home_swe_home.context import build_context

    f = tmp_path / "big.txt"
    f.write_text(
        "\n".join(f"line-{i}-" + "x" * 40 for i in range(2100)), encoding="utf-8"
    )
    ctx = await build_context(storage_dir=tmp_path / "sessions")
    result = await ctx.tools.execute(
        ToolCallData(call_id="big", name="read_file", arguments={"path": str(f)})
    )
    assert "[Output truncated" in result.content


@pytest.mark.asyncio
async def test_redaction_guard_applies_to_mounted_tools(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The mth redaction guard hides secrets from tool output."""
    from magitech_harness.session.events import ToolCallData

    from home_swe_home.context import build_context

    monkeypatch.setenv("NVIDIA_API_KEY", "super-secret-value")
    f = tmp_path / "env.txt"
    f.write_text("key=super-secret-value", encoding="utf-8")
    ctx = await build_context(storage_dir=tmp_path / "sessions")

    result = await ctx.tools.execute(
        ToolCallData(call_id="redacted", name="read_file", arguments={"path": str(f)})
    )
    assert "super-secret-value" not in result.content
    assert "<redacted>" in result.content
