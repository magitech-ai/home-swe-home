"""Command line interface for magecode.

Entry point only — all capabilities are Services mounted on the anima Context
assembled by ``build_context()``. The CLI loads config, builds the Context, and
starts headless or REPL mode.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .client import ConfigurationError, MiniClaudeError, create_client
from .context import build_context
from .core_loop import TurnInterrupted, TurnLimitReached
from .onboard import run_wizard
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
    parser.add_argument(
        "--init-home",
        nargs="?",
        const=str(Path.home() / ".agents" / "agents-home"),
        metavar="PATH",
        help="scaffold and provision a home checkout, then exit",
    )
    parser.add_argument(
        "--home-repo",
        default="",
        metavar="OWNER/NAME",
        help="repo to create with --init-home",
    )
    return parser


async def _run_headless(
    *,
    model: str,
    messages: list[dict[str, Any]],
) -> int:
    ctx = await build_context()
    try:
        await ctx.core_loop(model=model, messages=messages)
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

    # Load .env for local development. Existing env vars take precedence over
    # .env values: exported NVIDIA_API_KEY -> .env -> error.
    load_dotenv()

    if args.init_home is not None:
        if not args.home_repo:
            print("magecode: --init-home needs --home-repo OWNER/NAME", file=sys.stderr)
            return 2
        answer = input(f"Create {args.home_repo} at {args.init_home}? [y/N] ")
        accepted = run_wizard(
            Path(args.init_home),
            args.home_repo,
            confirm=lambda _question: answer.strip().lower().startswith("y"),
        )
        return 0 if accepted else 1

    if args.sandbox:
        os.environ["MAGECODE_SANDBOX"] = "1"

    # Fail fast on missing API key before assembling the Context.
    try:
        create_client()
    except ConfigurationError as error:
        print(f"magecode: {error}", file=sys.stderr)
        return 2

    ctx = await build_context()
    system_content = ctx.instructions.build(
        model=args.model, skills_catalog=ctx.skills.catalog()
    )
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]

    if args.prompt is not None:
        messages.append({"role": "user", "content": args.prompt})
        return await _run_headless(model=args.model, messages=messages)

    await run_repl(model=args.model, system_content=system_content, ctx=ctx)
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run_async(argv))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
