"""Per-repository verification commands.

A repo may declare its own checks in ``docs/agents/checks.md`` as a fenced
shell block. Otherwise the shared Python standards supply a default. These are
data helpers: execution belongs to the agent's tool loop, not this module.
"""

from __future__ import annotations

from pathlib import Path

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
