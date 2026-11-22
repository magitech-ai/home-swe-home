"""Command line interface for home-swe-home on magitech-harness.

Entry point only — all capabilities are Services on the mth Context assembled
by ``build_context()``. The CLI loads config, builds the Context, creates an
agent, and starts headless or REPL mode.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from magitech_harness.llm.message import create_user_message

from .context import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    build_context,
    default_model_for,
)
from .onboard import run_wizard
from .sandbox import set_sandbox_enabled
from .utils.home import find_home

DEFAULT_EFFORT = "medium"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="home-swe-home")
    parser.add_argument(
        "-p",
        "--prompt",
        metavar="TASK",
        help="run one task headless and exit",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "model id (default: provider-aware; "
            f"{DEFAULT_MODEL} for gemini, ERNIE flash for openrouter)"
        ),
    )
    parser.add_argument(
        "--effort",
        choices=("minimal", "low", "medium", "high"),
        default=os.environ.get("HOME_SWE_HOME_EFFORT", DEFAULT_EFFORT),
        help=f"reasoning effort (default: {DEFAULT_EFFORT})",
    )
    parser.add_argument(
        "--no-sandbox",
        dest="sandbox",
        action="store_false",
        default=True,
        help="run shell commands on the host instead of in a Docker sandbox",
    )
    parser.add_argument(
        "--show-reasoning",
        action="store_true",
        default=os.environ.get("HOME_SWE_HOME_SHOW_REASONING", "").lower()
        in {"1", "true", "yes"},
        help="display provider reasoning/thought summaries (never stored)",
    )
    parser.add_argument(
        "--init-home",
        nargs="?",
        const=str(Path.home() / ".agents" / "agents-home"),
        metavar="PATH",
        help="scaffold and provision a home checkout, then exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --init-home, scaffold and record config without GitHub writes",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="confirm onboarding non-interactively (for agents and scripts)",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="with --init-home, print the machine-readable plan without writing",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable output for --init-home",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow --init-home to replace an existing home pointer",
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
    model: str | None,
    prompt: str,
    effort: str = DEFAULT_EFFORT,
    session_id: str | None = None,
) -> int:
    """Run one headless task via mth's agent loop and return its exit code."""
    from magitech_harness.cli import summarize_headless_outcome

    ctx = await build_context()
    active_provider = os.environ.get("HOME_SWE_HOME_PROVIDER", DEFAULT_PROVIDER)
    active_model = model or default_model_for(active_provider)

    handle = await ctx.agents.create(
        {
            "sessionId": session_id or f"hsh-{uuid.uuid4()}",
            "agentOptions": {
                "provider": active_provider,
                "model": active_model,
                "reasoningEffort": effort,
            },
        }
    )
    agent = handle["agent"]
    first_seq = len(agent.session.events)

    agent.followup(
        create_user_message(
            content=[{"type": "text", "text": prompt}],
            source={"kind": "user"},
        )
    )
    await agent.when_idle()

    outcome = summarize_headless_outcome(agent.session, first_seq)
    print(outcome.text)
    if outcome.reason is not None and outcome.reason.get("kind") == "error":
        err = outcome.reason.get("error")
        if isinstance(err, dict):
            code = err.get("code", "UNKNOWN")
            msg = err.get("message", "")
            print(f"home-swe-home: {code}: {msg}", file=sys.stderr)
        return 1
    if outcome.reason is not None and outcome.reason.get("kind") == "completed":
        return 0
    return 1


async def _run_async(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    load_dotenv()

    if args.init_home is not None:
        if not args.home_repo:
            print(
                "home-swe-home: --init-home needs --home-repo OWNER/NAME",
                file=sys.stderr,
            )
            return 2
        from .onboard import plan_wizard

        plan = plan_wizard(Path(args.init_home), args.home_repo)
        if args.plan:
            if args.json:
                print(json.dumps(plan))
            else:
                for key, value in plan.items():
                    print(f"{key}: {value}")
            return 0
        if find_home() is not None and not args.force:
            print(
                "home-swe-home: a home checkout already exists; "
                "refusing to replace it (use --force to override)",
                file=sys.stderr,
            )
            return 2
        if args.yes:
            accepted_confirm = True
        else:
            answer = input(f"Create {args.home_repo} at {args.init_home}? [y/N] ")
            accepted_confirm = answer.strip().lower().startswith("y")
        accepted = run_wizard(
            Path(args.init_home),
            args.home_repo,
            confirm=lambda _question: accepted_confirm,
            dry_run=args.dry_run,
        )
        if args.json:
            print(json.dumps({"accepted": accepted, **plan}))
        elif accepted:
            print(f"Home scaffolded at {args.init_home}; next: review AGENTS.md.")
        return 0 if accepted else 1

    # The sandbox choice is an explicit setting, not a process-wide env
    # side effect: the run_command tool reads the same config key.
    set_sandbox_enabled(args.sandbox)

    # Fail fast on missing API key before assembling the Context.
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        print(
            "home-swe-home: GEMINI_API_KEY is not set. "
            "Export it: export GEMINI_API_KEY=<your key>",
            file=sys.stderr,
        )
        return 2

    if args.prompt is not None:
        return await _run_headless(
            model=args.model,
            prompt=args.prompt,
            effort=args.effort,
        )

    # Interactive REPL
    from .repl import run_repl

    await run_repl(
        model=args.model,
        show_reasoning=args.show_reasoning,
        effort=args.effort,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run_async(argv))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
