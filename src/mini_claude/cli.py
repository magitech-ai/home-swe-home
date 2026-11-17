"""Command line interface for mini-claude."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from dotenv import load_dotenv

from .client import ConfigurationError, MiniClaudeError, create_client
from .repl import run_repl
from .turn import TurnInterrupted, run_turn

DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mini-claude")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Load .env for local development. Existing environment variables take
    # precedence over .env values (python-dotenv default behavior), so the
    # fallback chain is: exported NVIDIA_API_KEY -> .env -> error.
    load_dotenv()

    try:
        client = create_client()
    except ConfigurationError as error:
        print(f"mini-claude: {error}", file=sys.stderr)
        return 2

    messages: list[dict[str, Any]] = []

    if args.prompt is not None:
        messages.append({"role": "user", "content": args.prompt})
        try:
            run_turn(model=args.model, messages=messages, client=client)
        except TurnInterrupted:
            print("\nTurn interrupted.", file=sys.stderr)
            return 130
        except MiniClaudeError as error:
            print(f"mini-claude: {error}", file=sys.stderr)
            return 1
        return 0

    run_repl(model=args.model, client=client)
    return 0
