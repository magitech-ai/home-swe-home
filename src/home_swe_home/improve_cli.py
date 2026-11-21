"""CLI for the Propose–Probe–Compose harness improvement loop.

``hsh-improve`` drives :func:`home_swe_home.orchestrate.run_cycle` from the
shell. It spends real inference and wall-clock: each candidate costs two CLI
rollouts per task per trial (base arm and candidate arm), so the default is one
trial and the caller decides when to raise it.

Nothing is auto-adopted into the installed package. On a win the command writes
a candidate tree under ``--work-dir/adopted`` and records the lesson in the
domain library; a human still decides whether to promote it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .eval import HARD_TASKS
from .orchestrate import ProposalError, build_proposer, default_ask, run_cycle
from .utils.harness import DEFAULT_HARNESS_DIR


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ``hsh-improve``."""
    parser = argparse.ArgumentParser(
        prog="hsh-improve",
        description="Run one measured harness-improvement cycle.",
    )
    parser.add_argument(
        "task",
        help="the task or observation to improve the harness for",
    )
    parser.add_argument(
        "--domain",
        default="general",
        help="domain label for the experience library (default: general)",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="harness tree to improve (default: active harness directory)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="where candidates and the adopted tree are written",
    )
    parser.add_argument(
        "--library-root",
        type=Path,
        default=None,
        help="root of the experience library (default: <work-dir>/library)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="interleaved trials per arm (default: 1)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the CycleReport as JSON here",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress progress lines (the final report still prints)",
    )
    return parser


def _on_event(message: str, *, quiet: bool) -> None:
    """Print a progress line unless the caller asked for quiet output."""
    if not quiet:
        print(message, file=sys.stderr, flush=True)


def _base_dir(value: Path | None) -> Path:
    """Resolve the harness tree to improve."""
    if value is not None:
        return value
    override = os.environ.get("HOME_SWE_HOME_HARNESS_DIR")
    return Path(override) if override else DEFAULT_HARNESS_DIR


def _work_dir(value: Path | None) -> Path:
    """Resolve the working directory for candidates and the adopted tree."""
    if value is not None:
        return value
    return Path(".hsh-improve")


def _report_payload(report: Any) -> dict[str, Any]:
    """Render a CycleReport to a JSON-serialisable dict."""
    return {
        "task": report.task,
        "domain": report.domain,
        "scores": report.scores,
        "winner": report.selection.winner,
        "reason": report.selection.reason,
        "adopted": report.adopted,
        "adopted_dir": str(report.adopted_dir) if report.adopted_dir else None,
        "base": {
            "passes": report.base.passes,
            "total": report.base.total,
            "trials": report.base.trials,
        },
        "candidate": (
            {
                "passes": report.candidate.passes,
                "total": report.candidate.total,
                "trials": report.candidate.trials,
            }
            if report.candidate is not None
            else None
        ),
        "rejection": report.rejection,
        "proposals": report.proposals,
    }


def main(argv: list[str] | None = None) -> int:
    """Run one improvement cycle. Exit 0 on any completed cycle, 2 on config error."""
    args = build_parser().parse_args(argv)

    if not os.environ.get("HOME_SWE_HOME_PROPOSER_MODEL"):
        print(
            "hsh-improve: HOME_SWE_HOME_PROPOSER_MODEL is not set; "
            "name the model that proposes harness candidates.",
            file=sys.stderr,
        )
        return 2
    if args.trials < 1:
        print("hsh-improve: --trials must be at least 1", file=sys.stderr)
        return 2

    base_dir = _base_dir(args.base_dir)
    if not base_dir.is_dir():
        print(f"hsh-improve: harness directory not found: {base_dir}", file=sys.stderr)
        return 2

    work_dir = _work_dir(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        report = run_cycle(
            task=args.task,
            domain=args.domain,
            base_dir=base_dir,
            work_dir=work_dir,
            tasks=HARD_TASKS,
            propose=build_proposer(default_ask),
            library_root=args.library_root,
            trials=args.trials,
            on_event=lambda message: _on_event(message, quiet=args.quiet),
        )
    except ProposalError as error:
        print(f"hsh-improve: {error}", file=sys.stderr)
        return 2

    payload = _report_payload(report)
    rendered = json.dumps(payload, indent=2)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
