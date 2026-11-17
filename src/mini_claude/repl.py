"""Interactive chat REPL."""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from .client import MiniClaudeError, create_client
from .core_loop import TurnInterrupted, TurnLimitReached, run_core_loop
from .instructions import build_system_instructions, count_tokens

PROMPT = "> "


def run_repl(
    *,
    model: str,
    client: OpenAI | None = None,
    system_content: str | None = None,
) -> None:
    """Run the interactive chat loop until the user exits with Ctrl-D."""
    client = client or create_client()  # validate configuration up front
    system_content = system_content or build_system_instructions(model=model)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    print("mini-claude interactive chat")
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
            _show_context(messages)
            continue

        messages.append({"role": "user", "content": text})
        try:
            run_core_loop(
                model=model,
                messages=messages,
                client=client,
                reply_prefix="< ",
                max_turns=20,
            )
        except TurnInterrupted:
            print("\nTurn interrupted.")
        except TurnLimitReached as error:
            print(f"\nmini-claude: {error}")
        except MiniClaudeError as error:
            print(f"\nmini-claude: {error}")


def _show_context(messages: list[dict[str, Any]]) -> None:
    """Print the context window contents and token counts."""
    total = count_tokens(messages)
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
