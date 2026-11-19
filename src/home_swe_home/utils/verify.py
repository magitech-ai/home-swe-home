"""Per-repository verification commands.

A repo may declare its own checks in ``docs/agents/checks.md`` as a fenced
shell block. Otherwise the shared Python standards supply a default. These are
data helpers: execution belongs to the agent's tool loop, not this module.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Runner = Callable[[str, Path], tuple[int, str]]


@dataclass(frozen=True)
class CheckResult:
    """One verification command and its outcome."""

    command: str
    ok: bool
    output: str


DEFAULT_CHECKS = (
    "uv sync --extra dev",
    "uv run ruff check src tests",
    "uv run mypy src",
    "uv run pytest",
)


def verification_commands(repo_root: Path) -> tuple[str, ...]:
    """Return the repo's declared checks, or the shared Python default."""
    path = Path(repo_root) / "docs" / "agents" / "checks.md"
    if not path.is_file():
        return DEFAULT_CHECKS

    commands: list[str] = []
    in_block = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("```sh") or stripped.startswith("```bash"):
            in_block = True
            continue
        if in_block and stripped.startswith("```"):
            break
        if in_block and stripped and not stripped.startswith("#"):
            commands.append(stripped)
    return tuple(commands) or DEFAULT_CHECKS


def default_runner(command: str, cwd: Path) -> tuple[int, str]:
    """Run one check in *cwd*, returning its exit code and combined output."""
    completed = subprocess.run(  # noqa: S603 - command is split, no shell
        shlex.split(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def run_checks(
    commands: tuple[str, ...], runner: Runner, *, cwd: Path = Path(".")
) -> list[CheckResult]:
    """Run each command in order, recording its outcome."""
    results: list[CheckResult] = []
    for command in commands:
        code, output = runner(command, cwd)
        results.append(CheckResult(command, code == 0, output))
    return results


def format_results(results: list[CheckResult]) -> str:
    """Render a compact pass/fail summary for the model."""
    if not results:
        return "No checks to run."
    lines: list[str] = []
    for result in results:
        lines.append(f"[{'PASS' if result.ok else 'FAIL'}] {result.command}")
        if not result.ok and result.output:
            lines.append(result.output[-800:])
    passed = sum(1 for result in results if result.ok)
    lines.append(f"{passed}/{len(results)} checks passed")
    return "\n".join(lines)
