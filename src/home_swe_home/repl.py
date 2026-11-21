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
    show_reasoning: bool = False,
    effort: str = "medium",
) -> None:
    """Run the interactive chat loop until the user exits with Ctrl-D."""
    import uuid

    ctx = await build_context()

    handle = await ctx.agents.create(
        {
            "sessionId": f"hsh-{uuid.uuid4()}",
            "agentOptions": {
                "provider": DEFAULT_PROVIDER,
                "model": model,
                "reasoningEffort": effort,
            },
        }
    )
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
    except Exception:  # pragma: no cover
        pass

    loop = asyncio.get_running_loop()
    sig_installed = False

    def _on_sigint() -> None:  # pragma: no cover
        agent.cancel({"kind": "user"})

    def _on_stream(payload: dict[str, Any]) -> None:  # pragma: no cover
        frame = payload.get("frame") or {}
        if frame.get("type") != "chunk":
            return
        chunk = frame.get("chunk") or {}
        if not isinstance(chunk, dict):
            return
        chunk_type = chunk.get("type")
        if chunk_type == "text-delta":
            text = chunk.get("text")
            if isinstance(text, str) and text:
                print(text, end="", flush=True)
        elif chunk_type == "reasoning-delta" and show_reasoning:
            text = chunk.get("text")
            if isinstance(text, str) and text:
                print(text, end="", flush=True)

    def _on_session_event(subject: Any, event: Any) -> None:  # pragma: no cover
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

    def _on_agent_error(payload: dict[str, Any]) -> None:  # pragma: no cover
        # mth's driver contains faults and emits agent/error instead of
        # raising, so surface failures here rather than silently printing
        # nothing.
        if payload.get("agent") is not agent:
            return
        error = payload.get("error")
        print(f"\n[Error: {error}]")

    stop_stream = ctx.on("agent/assistant-stream", _on_stream)
    stop_events = ctx.on("session/event", _on_session_event)
    stop_errors = ctx.on("agent/error", _on_agent_error)

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
                current_model = text[len("/model ") :].strip()
                agent.model.select(
                    {
                        "provider": DEFAULT_PROVIDER,
                        "model": current_model,
                    }
                )
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
                    print(skills.load(text[len("/skill ") :].strip()))
                else:
                    print("No skills service mounted.")
                continue

            sig_installed = _install_sigint(loop, _on_sigint, sig_installed)

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
        stop_errors()
        # Unconditional: _remove_sigint is safe when nothing was installed, so
        # the cleanup runs on every platform (including ones where installing
        # a SIGINT handler is unsupported, e.g. Windows).
        _remove_sigint(loop)


def _install_sigint(loop: Any, handler: Any, installed: bool = False) -> bool:
    """Install a SIGINT handler once, reporting whether one is active.

    ``loop.add_signal_handler`` is unavailable on some platforms (notably
    Windows, which raises ``NotImplementedError``), so this returns False
    rather than raising and the REPL keeps running without Ctrl-C handling.
    The ``installed`` argument keeps the state in one place, so the caller has
    no platform-dependent branch of its own.
    """
    if installed:
        return True
    try:
        loop.add_signal_handler(py_signal.SIGINT, handler)
    except (NotImplementedError, RuntimeError, AttributeError, ValueError, OSError):
        return False
    return True


def _remove_sigint(loop: Any) -> None:
    """Remove a previously installed SIGINT handler, ignoring failures."""
    try:
        loop.remove_signal_handler(py_signal.SIGINT)
    except (RuntimeError, ValueError, OSError, KeyError):
        pass


def _show_context(agent: Any) -> None:
    """Print the context window: each message with a preview, plus tokens."""
    from magitech_harness import derive_messages

    messages = derive_messages(list(agent.session.events))
    total = _estimate_tokens(messages)
    print(f"--- context window: {len(messages)} messages, ~{total} tokens ---")
    for index, message in enumerate(messages):
        role = message.get("role", "?")
        content = message.get("content") or ""
        text = _text_preview(content)
        print(f"[{index}] {role}: {text}")


def _text_preview(content: Any, limit: int = 200) -> str:
    """Join text blocks and truncate for display."""
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        parts = [
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
    else:
        parts = []
    text = " ".join(part for part in parts if part).strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate: ~4 characters per token."""
    total = 0
    for message in messages:
        total += len(str(message.get("role", "")))
        total += len(_text_preview(message.get("content") or "", limit=10**9))
    return total // 4
