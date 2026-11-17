"""Command line interface for magecode."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

from dotenv import load_dotenv

from .client import ConfigurationError, MiniClaudeError, create_client
from .context import build_context
from .core_loop import TurnInterrupted, TurnLimitReached
from .instructions import build_system_instructions
from .repl import run_repl

DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="magecode")
    parser.add_argument(
        "-p",
        "--prompt",
        metavar="TASK",
        help="run one task headless and exit",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="run shell commands in a Docker sandbox (default: host execution)",
    )
    return parser


async def _run_headless(
    *,
    model: str,
    messages: list[dict[str, Any]],
    client: Any,
) -> int:
    ctx = await build_context()
    try:
        await ctx.core_loop(
            model=model,
            messages=messages,
            client=client,
        )
    except TurnInterrupted:
        print("\nTurn interrupted.", file=sys.stderr)
        return 130
    except TurnLimitReached as error:
        print(f"\nmagecode: {error}", file=sys.stderr)
        return 1
    except MiniClaudeError as error:
        print(f"\nmagecode: {error}", file=sys.stderr)
        return 1
    return 0


async def _run_async(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Load .env for local development. Existing environment variables take
    # precedence over .env values (python-dotenv default behavior), so the
    # fallback chain is: exported NVIDIA_API_KEY -> .env -> error.
    load_dotenv()

    # Opt-in sandboxing for shell commands. Set via --sandbox flag or
    # MAGECODE_SANDBOX env var; checked at run_command call time.
    if args.sandbox:
        os.environ["MAGECODE_SANDBOX"] = "1"

    try:
        client = create_client()
    except ConfigurationError as error:
        print(f"magecode: {error}", file=sys.stderr)
        return 2

    system_content = build_system_instructions(model=args.model)

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]

    if args.prompt is not None:
        messages.append({"role": "user", "content": args.prompt})
        return await _run_headless(model=args.model, messages=messages, client=client)

    ctx = await build_context()
    await run_repl(
        model=args.model, client=client, system_content=system_content, ctx=ctx
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run_async(argv))
