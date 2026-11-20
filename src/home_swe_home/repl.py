"""Interactive chat REPL for home-swe-home on magitech-harness.

Capabilities come from the mth Context: ``ctx.agents`` for the turn loop,
``ctx.llm`` for the model adapter, and ``ctx.tools`` for tool execution.
All tools and the model adapter are registered in ``build_context()``.
"""

from __future__ import annotations

import asyncio
import signal as py_signal
from typing import Any

from magitech_harness.llm.message import create_user_message

from .context import DEFAULT_MODEL, DEFAULT_PROVIDER, build_context

PROMPT = "> "


async def run_repl(
    *,
    model: str = DEFAULT_MODEL,
    stream: bool = True,
    show_reasoning: bool = False,
    show_events: bool = False,
    effort: str = "medium",
) -> None:
    """Run the interactive chat loop until the user exits with Ctrl-D."""
    import uuid

    ctx = await build_context()

    handle = await ctx.agents.create({
        "sessionId": f"hsh-{uuid.uuid4()}",
        "agentOptions": {
            "provider": DEFAULT_PROVIDER,
            "model": model,
            "reasoningEffort": effort,
        },
    })
    agent = handle["agent"]
    current_model = model

    print("home-swe-home interactive chat (on magitech-harness)")
    print("  /model <id>   switch model")
    print("  /context      show context window and token counts")
    print("  /reminders    show passive due/upcoming reminders")
    print("  /skill <name> load a skill's full instructions")
    print("  Ctrl-C        cancel current turn")
    print("  Ctrl-D        exit")
    print(f"  model: {current_model}")

    # Show reminder summary if any.
    try:
        reminders = ctx.get("reminders", None, strict=False)
        if reminders is not None:
            summary = reminders.summary_line()
            if summary:
                print(summary)
    except Exception:
        pass

    loop = asyncio.get_running_loop()
    sig_installed = False

    def _on_sigint() -> None:
        agent.cancel({"kind": "user"})

    def _on_stream(payload: dict[str, Any]) -> None:
        frame = payload.get("frame") or {}
        if frame.get("type") != "chunk":
            return
        chunk = frame.get("chunk") or {}
        if isinstance(chunk, dict):
            text = chunk.get("text")
            if isinstance(text, str) and text:
                print(text, end="", flush=True)

    def _on_session_event(subject: Any, event: Any) -> None:
        from magitech_harness import EventType
        if subject is not agent.session:
            return
        if event.type == EventType.TOOL_CALL:
            payload = event.payload or {}
            print(f"\n[tool: {payload.get('name')}]")
        elif event.type == EventType.TOOL_RESULT:
            payload = event.payload or {}
            status = "ERROR" if payload.get("is_error") else "OK"
            print(f"\n[{status}] {payload.get('name')}")

    stop_stream = ctx.on("agent/assistant-stream", _on_stream)
    stop_events = ctx.on("session/event", _on_session_event)

    try:
        while True:
            try:
                user_input = await asyncio.to_thread(input, PROMPT)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue

            text = user_input.strip()
            if not text:
                continue

            if text == "/model":
                print(f"model: {current_model}")
                continue
            if text.startswith("/model "):
                current_model = text[len("/model "):].strip()
                agent.model.select({
                    "provider": DEFAULT_PROVIDER,
                    "model": current_model,
                })
                print(f"model: {current_model}")
                continue
            if text == "/context":
                _show_context(agent)
                continue
            if text == "/reminders":
                reminders = ctx.get("reminders", None, strict=False)
                if reminders is not None:
                    print(reminders.report())
                else:
                    print("No reminders service mounted.")
                continue
            if text.startswith("/skill "):
                skills = ctx.get("skills", None, strict=False)
                if skills is not None:
                    print(skills.load(text[len("/skill "):].strip()))
                else:
                    print("No skills service mounted.")
                continue

            if not sig_installed:
                try:
                    loop.add_signal_handler(py_signal.SIGINT, _on_sigint)
                    sig_installed = True
                except (NotImplementedError, RuntimeError, AttributeError):
                    pass

            agent.followup(
                create_user_message(
                    content=[{"type": "text", "text": text}],
                    source={"kind": "user"},
                )
            )
            try:
                await agent.when_idle()
                print()
            except Exception as e:
                print(f"\n[Error during turn: {e}]")
    finally:
        stop_stream()
        stop_events()
        if sig_installed:
            try:
                loop.remove_signal_handler(py_signal.SIGINT)
            except (RuntimeError, ValueError, OSError):
                pass


def _show_context(agent: Any) -> None:
    """Print the context window contents and token counts."""
    session = agent.session
    print(f"--- context window: {len(session.events)} events ---")
    for index, event in enumerate(session.events):
        print(f"[{index}] {event.type}")
    print("--- end context ---")