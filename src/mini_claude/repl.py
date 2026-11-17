"""Interactive chat REPL."""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from .client import MiniClaudeError, create_client
from .turn import TurnInterrupted, run_turn

PROMPT = "> "


def run_repl(*, model: str, client: OpenAI | None = None) -> None:
    """Run the interactive chat loop until the user exits with Ctrl-D."""
    client = client or create_client()  # validate configuration up front
    messages: list[dict[str, Any]] = []
    print("mini-claude interactive chat")
    print("  /model <id>   switch model")
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

        messages.append({"role": "user", "content": text})
        try:
            run_turn(model=model, messages=messages, client=client)
        except TurnInterrupted:
            print("\nTurn interrupted.")
        except MiniClaudeError as error:
            print(f"\nmini-claude: {error}")
