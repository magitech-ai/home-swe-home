"""The core turn loop.

Ask the model, append its reply exactly as it came back, run any tools it
requests, feed the results back, and repeat until the model stops asking for
tools. Ctrl-C aborts the current turn only.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from .client import chat_complete, create_client
from .tools import CHAT_COMPLETION_TOOLS, execute_tool


class TurnInterrupted(Exception):
    """The user aborted the current turn with Ctrl-C."""


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


def run_turn(
    *,
    model: str,
    messages: list[dict[str, Any]],
    client: OpenAI | None = None,
) -> list[dict[str, Any]]:
    """Run one turn until the model stops asking for tools.

    ``messages`` is mutated and returned. Model replies are appended exactly as
    they came back; tool results are appended as ``tool`` messages. Raises
    ``TurnInterrupted`` if the user hits Ctrl-C during this turn.
    """
    client = client or create_client()
    try:
        while True:
            response = chat_complete(
                client,
                model=model,
                messages=messages,
                tools=CHAT_COMPLETION_TOOLS,
            )

            assistant_message = response.choices[0].message
            messages.append(_assistant_message_dict(assistant_message))

            if assistant_message.content:
                print(f"< {assistant_message.content}", end="")

            tool_calls = getattr(assistant_message, "tool_calls", None) or []
            if not tool_calls:
                print()
                return messages

            print()  # separate the reply from tool activity
            for tool_call in tool_calls:
                name = tool_call.function.name
                print(f"[tool: {name}]")
                result = execute_tool(name, tool_call.function.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )
    except KeyboardInterrupt:
        raise TurnInterrupted() from None
