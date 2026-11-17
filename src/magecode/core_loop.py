"""The core turn loop.

Ask the model, append its reply exactly as it came back, run any tools it
requests, feed the results back, and repeat until the model stops asking for
tools. Ctrl-C aborts the current turn only.

Implemented as an anima Service component mounted on a Context. Tool calls are
dispatched through the context's service registry via ``execute_tool``.
"""

from __future__ import annotations

from typing import Any

from anima import Context, Service
from openai import OpenAI

from .client import chat_complete
from .instructions import count_tokens
from .tools import execute_tool, service_schema


class TurnInterrupted(Exception):
    """The user aborted the current turn with Ctrl-C."""


class TurnLimitReached(Exception):
    """The turn exceeded the maximum number of model calls."""


class CoreLoopService(Service):
    """Core turn loop: send task to model, run tools, repeat."""

    def __init__(self, ctx: Context):
        super().__init__(ctx, "core_loop")

    async def __call__(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        client: OpenAI,
        reply_prefix: str = "",
        max_turns: int = 20,
    ) -> list[dict[str, Any]]:
        """Run one turn until the model stops asking for tools.

        ``messages`` is mutated and returned. Model replies are appended
        exactly as they came back; tool results are appended as ``tool``
        messages. Raises ``TurnInterrupted`` if the user hits Ctrl-C during
        this turn. Raises ``TurnLimitReached`` if ``max_turns`` model calls
        are made without a final answer.

        ``reply_prefix`` is printed before assistant content (chat mode uses
        ``< ``; headless leaves it empty so output stays raw).  The token
        count is printed only in headless mode (``reply_prefix == ""``).
        """
        read_files: set[str] = set()
        turn_count = 0
        is_headless = reply_prefix == ""
        try:
            while True:
                turn_count += 1
                if turn_count > max_turns:
                    raise TurnLimitReached(
                        f"Turn limit of {max_turns} model calls reached without "
                        "a final answer."
                    )

                tokens = count_tokens(messages)
                if is_headless:
                    print(f"[context: {tokens} tokens]")
                response = chat_complete(
                    client,
                    model=model,
                    messages=messages,
                    tools=_tool_schemas_from_ctx(self.ctx),
                )

                assistant_message = response.choices[0].message
                messages.append(_assistant_message_dict(assistant_message))

                if assistant_message.content:
                    print(f"{reply_prefix}{assistant_message.content}", end="")

                tool_calls = getattr(assistant_message, "tool_calls", None) or []
                if not tool_calls:
                    print()
                    return messages

                print()  # separate the reply from tool activity
                for tool_call in tool_calls:
                    name = tool_call.function.name
                    print(f"[tool: {name}]")
                    result = execute_tool(
                        self.ctx,
                        name,
                        tool_call.function.arguments,
                        read_files=read_files,
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )
        except KeyboardInterrupt:
            raise TurnInterrupted() from None


def _tool_schemas_from_ctx(ctx: Context) -> list[dict[str, Any]]:
    """Build OpenAI-compatible schemas for all mounted tool services."""
    schemas: list[dict[str, Any]] = []
    for impl in ctx.reflect.store.values():
        service = impl.value
        schemas.append(service_schema(type(service), name=impl.name))
    return schemas


def _assistant_message_dict(message: Any) -> dict[str, Any]:
    """Convert one model message into a storable message dict, verbatim."""
    result: dict[str, Any] = {"role": message.role or "assistant"}
    if message.content is not None:
        result["content"] = message.content
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        result["tool_calls"] = [
            {
                "id": call.id,
                "type": call.type,
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in tool_calls
        ]
    return result
