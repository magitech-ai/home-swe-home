"""Interactive chat REPL.

Entry point for interactive mode. Capabilities come from the anima Context:
``ctx.instructions`` for prompt assembly and token counts, ``ctx.core_loop``
for turns. All tools and the model adapter are mounted on the Context.
"""

from __future__ import annotations

from typing import Any

from anima import Context

from .client import MiniClaudeError
from .context import build_context
from .core_loop import TurnInterrupted, TurnLimitReached

PROMPT = "> "


async def run_repl(
    *,
    model: str,
    system_content: str | None = None,
    ctx: Context | None = None,
    stream: bool = True,
    show_reasoning: bool = False,
    show_events: bool = False,
    effort: str = "medium",
) -> None:
    """Run the interactive chat loop until the user exits with Ctrl-D."""
    ctx = ctx or await build_context()
    system_content = system_content or ctx.instructions.build(model=model)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    print("home-swe-home interactive chat")
    print("  /model <id>   switch model")
    print("  /context      show context window and token counts")
    print("  Ctrl-D        exit")
    print(f"  model: {model}")
    while True:
        try:
            user_input = input(PROMPT)
        except EOFError:
            print()
            return
        except KeyboardInterrupt:
            print()
            continue

        text = user_input.strip()
        if not text:
            continue
        if text == "/model":
            print(f"model: {model}")
            continue
        if text.startswith("/model "):
            model = text[len("/model ") :].strip()
            print(f"model: {model}")
            continue
        if text == "/context":
            _show_context(messages, ctx)
            continue
        if text.startswith("/skill "):
            print(ctx.skills.load(text[len("/skill ") :].strip()))
            continue

        messages.append({"role": "user", "content": text})
        try:
            await ctx.core_loop(
                model=model,
                messages=messages,
                reply_prefix="< ",
                max_turns=20,
                stream=stream,
                show_reasoning=show_reasoning,
                show_events=show_events,
                effort=effort,
            )
        except TurnInterrupted:
            print("\nTurn interrupted.")
        except TurnLimitReached as error:
            print(f"\nhome-swe-home: {error}")
        except MiniClaudeError as error:
            print(f"\nhome-swe-home: {error}")


def _show_context(messages: list[dict[str, Any]], ctx: Context) -> None:
    """Print the context window contents and token counts."""
    total = ctx.instructions.count(messages)
    print(f"--- context window: {len(messages)} messages, {total} tokens ---")
    for index, message in enumerate(messages):
        role = message.get("role", "?")
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls")
        prefix = f"[{index}] {role}"
        if tool_calls:
            prefix += f" ({len(tool_calls)} tool call(s))"
        print(prefix)
        if content:
            print(content[:200] + ("..." if len(content) > 200 else ""))
        if tool_calls:
            for call in tool_calls:
                func = call.get("function", {})
                print(f"  tool: {func.get('name')} args={func.get('arguments')[:80]}")
    print("--- end context ---")
