"""The core turn loop as an anima Service component.

Ask the model, append its reply verbatim, run any tools it requests, feed the
results back, and repeat until the model stops asking. Ctrl-C aborts the turn
only. Every capability is reached through the Context: ``ctx.client``,
``ctx.instructions``, ``ctx.tools``.
"""

from __future__ import annotations

from typing import Any

from anima import Context, Service

from .tools import TOOL_SERVICES
from .utils.harness import tool_guidance
from .utils.schema import service_schema
from .utils.stream import consume_stream


class TurnInterrupted(Exception):
    """The user aborted the current turn with Ctrl-C."""


class TurnLimitReached(Exception):
    """The turn exceeded the maximum number of model calls."""


class CoreLoopService(Service):
    """Core turn loop: send task to model, run tools, repeat."""

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "core_loop")

    async def __call__(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        reply_prefix: str = "",
        max_turns: int = 20,
        stream: bool = False,
    ) -> list[dict[str, Any]]:
        """Run one turn until the model stops asking for tools.

        ``messages`` is mutated and returned. Model replies are appended
        verbatim; tool results as ``tool`` messages. Raises ``TurnInterrupted``
        on Ctrl-C and ``TurnLimitReached`` after ``max_turns`` calls without a
        final answer. The token count prints only in headless mode.

        ``reply_prefix`` is printed before assistant content (``"< "`` in
        chat mode); headless leaves it empty so output stays raw. With
        ``stream=True`` content deltas are printed as they arrive.
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

                tokens = self.ctx.instructions.count(messages)
                if is_headless:
                    print(f"[context: {tokens} tokens]")
                tools = self._tool_schemas()
                if stream:
                    print(reply_prefix, end="", flush=True)
                    response = self.ctx.client.chat_stream(
                        model=model, messages=messages, tools=tools
                    )
                    assistant_message = consume_stream(
                        response, on_delta=lambda text: print(text, end="", flush=True)
                    )
                else:
                    response = self.ctx.client.chat_complete(
                        model=model, messages=messages, tools=tools
                    )
                    assistant_message = response.choices[0].message
                    if assistant_message.content:
                        print(f"{reply_prefix}{assistant_message.content}", end="")

                messages.append(_assistant_message_dict(assistant_message))

                tool_calls = getattr(assistant_message, "tool_calls", None) or []
                if not tool_calls:
                    print()
                    return messages

                print()  # separate the reply from tool activity
                for tool_call in tool_calls:
                    name = tool_call.function.name
                    print(f"[tool: {name}]")
                    result = self.ctx.tools.execute(
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

    def _tool_schemas(self) -> list[dict[str, Any]]:
        """Build OpenAI-compatible schemas for all mounted tool services."""
        return [
            service_schema(
                type(impl.value), name=impl.name, guidance=tool_guidance(impl.name)
            )
            for impl in self.ctx.reflect.store.values()
            if isinstance(impl.value, TOOL_SERVICES)
        ]


def _assistant_message_dict(message: Any) -> dict[str, Any]:
    """Convert one model message into a storable message dict, verbatim."""
    result: dict[str, Any] = {"role": message.role or "assistant"}
    if message.content is not None:
        result["content"] = message.content
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        entries: list[dict[str, Any]] = []
        for call in tool_calls:
            entry: dict[str, Any] = {
                "id": call.id,
                "type": call.type,
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            # Gemini thinking models attach an encrypted thought signature to
            # each tool call; dropping it makes the follow-up turn fail with
            # HTTP 400. Preserve it verbatim when the provider supplies one.
            extra = getattr(call, "extra_content", None)
            if extra is not None:
                entry["extra_content"] = extra
            entries.append(entry)
        result["tool_calls"] = entries
    return result
