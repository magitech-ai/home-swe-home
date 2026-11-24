"""External Propose–Probe–Compose step for harness improvement.

This module is a library for an external orchestrator, not an animas Service.
The proposer and rollout runner are injected, so tests need no model or network.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .utils.harness import read_tree, validate_tree, write_tree

Proposer = Callable[[str, dict[str, str]], dict[str, str]]
Runner = Callable[[Path, str], str]


@dataclass(frozen=True)
class StepResult:
    """Outcome of one improvement step."""

    accepted: bool
    error: str
    candidate: Path | None
    rollout: str


def default_runner(candidate: Path, task: str) -> str:
    """Probe a candidate harness by running the home-swe-home CLI once."""
    env = os.environ.copy()
    env["HOME_SWE_HOME_HARNESS_DIR"] = str(candidate)
    completed = subprocess.run(  # noqa: S603 - fixed command, no shell
        [sys.executable, "-m", "home_swe_home.cli", "-p", task],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    return completed.stdout + completed.stderr


def run_step(
    *,
    base_dir: Path,
    work_dir: Path,
    task: str,
    propose: Proposer,
    run: Runner = default_runner,
) -> StepResult:
    """Propose a candidate, validate it, then probe it once."""
    base = read_tree(base_dir)
    candidate = propose(task, dict(base))
    error = validate_tree(candidate)
    if error:
        return StepResult(accepted=False, error=error, candidate=None, rollout="")
    written = write_tree(candidate, work_dir / "harness")
    return StepResult(
        accepted=True, error="", candidate=written, rollout=run(written, task)
    )


@dataclass(frozen=True)
class CycleResult:
    """The measured outcome of one full improvement cycle."""

    scores: dict[str, float]
    selection: object
    final: dict[str, str]
    final_dir: Path


Evaluator = Callable[[Path, object], float]


def run_cycle(
    *,
    base_dir: Path,
    work_dir: Path,
    tasks: object,
    candidates: dict[str, dict[str, str]],
    evaluate_fn: Evaluator,
) -> CycleResult:
    """Probe every candidate, select a strict winner, compose and persist it."""
    from .utils.selection import compose, select

    base = read_tree(base_dir)
    scores: dict[str, float] = {}
    valid: dict[str, dict[str, str]] = {}
    for name, tree in candidates.items():
        if validate_tree(tree):
            continue
        valid[name] = tree
        candidate_dir = write_tree(tree, work_dir / "candidates" / name)
        scores[name] = evaluate_fn(candidate_dir, tasks)

    selection = select(scores)
    final = compose(base, valid, scores)
    final_dir = write_tree(final, work_dir / "final")
    return CycleResult(scores, selection, final, final_dir)
