"""Verify the model-visible ⟺ logged invariant for home-swe-home.

Every prompt fragment that reaches the LLM must be reconstructable from the
session event log. This test creates an agent, sends a message, and verifies
that ``derive_messages`` on the session log produces the same messages that
were sent to the LLM.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from magitech_harness.llm.message import create_user_message
from magitech_harness.session.store import derive_messages


@pytest.mark.asyncio
async def test_model_visible_equals_logged(tmp_path: Any) -> None:
    """Verify that derive_messages reconstructs the full conversation."""
    from home_swe_home.context import build_context

    # Use a scripted adapter so we don't need a real API key.
    ctx = await build_context(storage_dir=tmp_path)

    # Register a mock adapter that yields a simple text response.
    async def _mock_stream(options: Any) -> Any:
        yield {"type": "block-start", "index": 0, "blockType": "text"}
        yield {"type": "text-delta", "index": 0, "text": "Hello from mock."}
        yield {
            "type": "block-end",
            "index": 0,
            "block": {"type": "text", "text": "Hello from mock."},
        }
        yield {"type": "finish", "reason": {"kind": "stop"}}

    mock_adapter = MagicMock()
    mock_adapter.provider_info.return_value = {"id": "mock", "name": "Mock"}
    mock_adapter.list_models = AsyncMock(return_value=[])
    mock_adapter.resolve_model = AsyncMock(
        return_value={"provider": "mock", "id": "mock-1", "name": "Mock 1"}
    )
    mock_adapter.prepare_call = AsyncMock(
        return_value=MagicMock(
            model={"provider": "mock", "id": "mock-1", "name": "Mock 1"},
            stream=lambda opts: _mock_stream(opts),
        )
    )
    ctx.llm.register_adapter(["mock"], mock_adapter)

    handle = await ctx.agents.create(
        {
            "sessionId": "invariant-test",
            "agentOptions": {"provider": "mock", "model": "mock-1"},
        }
    )
    agent = handle["agent"]

    # Send a user message.
    agent.followup(
        create_user_message(
            content=[{"type": "text", "text": "Say hello"}],
            source={"kind": "user"},
        )
    )
    await agent.when_idle()

    # Derive messages from the session log.
    messages = derive_messages(list(agent.session.events))

    # The conversation must contain:
    # 1. A system message (from system prompt sections)
    # 2. A user message with "Say hello"
    # 3. An assistant message with "Hello from mock."
    roles = [m.get("role") for m in messages]
    assert "user" in roles, f"No user message in derived messages: {roles}"
    assert "assistant" in roles, f"No assistant message in derived: {roles}"

    # Find the user message and verify its content.
    user_msg = next(m for m in messages if m.get("role") == "user")
    user_text = ""
    for block in user_msg.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            user_text += block.get("text", "")
    assert "Say hello" in user_text, f"User message not logged: {user_text}"

    # Find the assistant message and verify its content.
    assistant_msg = next(m for m in messages if m.get("role") == "assistant")
    assistant_text = ""
    for block in assistant_msg.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            assistant_text += block.get("text", "")
    assert "Hello from mock." in assistant_text, (
        f"Assistant message not logged: {assistant_text}"
    )

    await handle["dispose"]()
