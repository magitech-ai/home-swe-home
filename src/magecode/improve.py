"""External Propose–Probe–Compose step for harness improvement.

This module is a library for an external orchestrator, not an anima Service.
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
    """Probe a candidate harness by running the magecode CLI once."""
    env = os.environ.copy()
    env["MAGECODE_HARNESS_DIR"] = str(candidate)
    completed = subprocess.run(  # noqa: S603 - fixed command, no shell
        [sys.executable, "-m", "magecode.cli", "-p", task],
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
