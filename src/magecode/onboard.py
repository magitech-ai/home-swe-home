"""First-run onboarding for a home checkout.

The wizard only performs steps that need a human decision; authentication is
delegated to ``gh`` and every remote side effect is confirmed explicitly.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from .utils.harness import DEFAULT_HARNESS_DIR
from .utils.home import find_home, save_config

AGENTS_TEMPLATE = """# Agents Home

The shared workspace for agent guidance and coordinated work across projects.
Start agent sessions here when a task may span multiple repositories.

## Other Repos

- **example** (example repository): `../example`. Clone from
  <https://github.com/your-org/example.git> if missing. Read its `AGENTS.md`
  before changes.
"""

SKILLS_TEMPLATE = """# Shared Skills

Each skill lives directly under `skills/` so tools that scan one level deep can
discover it. This repository is the canonical source.
"""

Confirm = Callable[[str], bool]
Runner = Callable[[tuple[str, ...]], object]


def needs_onboarding() -> bool:
    """Whether no home checkout is discoverable."""
    return find_home() is None


def scaffold(root: Path, harness_dir: Path = DEFAULT_HARNESS_DIR) -> list[Path]:
    """Create the starter files for a home checkout, preserving existing ones."""
    destination = Path(root)
    (destination / "skills").mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for relative, content in (
        ("AGENTS.md", AGENTS_TEMPLATE),
        ("skills/README.md", SKILLS_TEMPLATE),
    ):
        path = destination / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(path)
    for source in sorted(Path(harness_dir).glob("*.md")):
        target = destination / "harness" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            created.append(target)
    return created


def provision_commands(repo: str, root: Path) -> tuple[tuple[str, ...], ...]:
    """Return the GitHub commands for provisioning a private home repo."""
    location = str(Path(root))
    return (
        ("gh", "auth", "status"),
        ("gh", "repo", "view", repo, "--json", "nameWithOwner"),
        ("gh", "repo", "create", repo, "--private"),
        ("git", "-C", location, "init"),
        (
            "git",
            "-C",
            location,
            "remote",
            "add",
            "origin",
            f"https://github.com/{repo}.git",
        ),
        ("git", "-C", location, "add", "."),
        ("git", "-C", location, "commit", "-m", "Initialize agents home"),
        ("git", "-C", location, "push", "-u", "origin", "main"),
    )


def default_runner(command: tuple[str, ...]) -> None:
    """Run one provisioning command, failing loudly on error."""
    subprocess.run(command, check=True)


def plan_wizard(root: Path, repo: str) -> dict[str, object]:
    """Return a machine-readable plan for an onboarding run."""
    return {
        "root": str(Path(root).expanduser()),
        "repo": repo,
        "files": [
            str(path)
            for path in (
                Path(root) / "AGENTS.md",
                Path(root) / "skills" / "README.md",
                Path(root) / "harness" / "systemprompt.md",
                Path(root) / "harness" / "tool_guidance.md",
            )
        ],
        "commands": [" ".join(command) for command in provision_commands(repo, root)],
        "config": str(Path(root).resolve()),
    }


def run_wizard(
    root: Path,
    repo: str,
    *,
    confirm: Confirm,
    runner: Runner = default_runner,
    dry_run: bool = False,
) -> bool:
    """Scaffold and provision a home checkout, returning whether it ran."""
    question = (
        f"Create {repo} at {Path(root).expanduser()} and push it as a private repo?"
    )
    if not confirm(question):
        return False
    scaffold(root)
    if not dry_run:
        for command in provision_commands(repo, root):
            runner(command)
    save_config(home_path=Path(root), repo=repo)
    return True
