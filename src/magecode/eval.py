"""A/B evaluation of harness candidates on a fixed task suite.

A harness change is adopted only when its pass rate improves on the same tasks
as the base harness. Task checkers look for evidence in the CLI transcript;
the runner is injected so tests need no model or network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

HarnessRunner = Callable[[str, Path | None], str]


@dataclass(frozen=True)
class Task:
    """One evaluation task and the transcript marker that proves success."""

    id: str
    prompt: str
    expected: str


BUILTIN_TASKS = (
    Task("plain-reply", "Reply with exactly: PONG", "PONG"),
    Task(
        "add-repo",
        "Call the add_repo tool with ref='magecode' and confirm=false. "
        "Report exactly what the tool returns.",
        "Resolved 'magecode'",
    ),
    Task(
        "run-command",
        "Use run_command to run: echo EVAL-OK. Report the output.",
        "EVAL-OK",
    ),
    Task(
        "load-skill",
        "Call the load_skill tool with name='tdd'. Report what you loaded.",
        "[tool: load_skill]",
    ),
)


@dataclass(frozen=True)
class EvalResult:
    """Outcomes for one harness across all tasks and trials."""

    harness: str
    trials: int
    passes: int
    total: int
    failures: tuple[str, ...]

    @property
    def pass_rate(self) -> float:
        return self.passes / self.total if self.total else 0.0


def evaluate(
    tasks: tuple[Task, ...],
    runner: HarnessRunner,
    *,
    harness: str = "base",
    harness_dir: Path | None = None,
    trials: int = 1,
) -> EvalResult:
    """Run every task *trials* times and count successful transcripts."""
    passes = 0
    failures: list[str] = []
    for task in tasks:
        for trial in range(1, trials + 1):
            transcript = runner(task.prompt, harness_dir)
            label = f"{task.id}/t{trial}"
            if task.expected in transcript:
                passes += 1
            else:
                failures.append(label)
    return EvalResult(
        harness=harness,
        trials=trials,
        passes=passes,
        total=len(tasks) * trials,
        failures=tuple(failures),
    )


def compare(base: EvalResult, candidate: EvalResult) -> dict[str, object]:
    """Return the measured delta; no judgement is made here."""
    return {
        "base": base.pass_rate,
        "candidate": candidate.pass_rate,
        "delta": candidate.pass_rate - base.pass_rate,
        "base_failures": list(base.failures),
        "candidate_failures": list(candidate.failures),
    }


def write_report(results: tuple[EvalResult, ...], path: Path) -> Path:
    """Persist results as JSON for later inspection."""
    payload = [
        {
            "harness": result.harness,
            "trials": result.trials,
            "passes": result.passes,
            "total": result.total,
            "pass_rate": result.pass_rate,
            "failures": list(result.failures),
        }
        for result in results
    ]
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination


def cli_runner(task: str, harness_dir: Path | None) -> str:
    """Run one task against an optional candidate harness via the CLI."""
    env = os.environ.copy()
    env.pop("MAGECODE_HARNESS_DIR", None)
    if harness_dir is not None:
        env["MAGECODE_HARNESS_DIR"] = str(harness_dir)
    completed = subprocess.run(  # noqa: S603 - fixed command, no shell
        [sys.executable, "-m", "magecode.cli", "-p", task],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    return completed.stdout + completed.stderr
