"""Issue-tracker contract for target repositories.

The org default is GitHub via ``gh`` with the canonical five-role vocabulary
(``.github/CONTRIBUTING.md``). A repo's ``docs/agents/issue-tracker.md``
overrides it; when that file is absent the built-in default applies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_LABELS = (
    "needs-triage",
    "needs-info",
    "ready-for-agent",
    "ready-for-human",
    "wontfix",
)


@dataclass(frozen=True)
class TrackerConfig:
    """How this repo's issues and PRs are tracked."""

    kind: str
    cli: str
    labels: tuple[str, ...]
    source: str


def load_tracker(repo_root: Path) -> TrackerConfig:
    """Return the repo's tracker config, falling back to the org default."""
    path = Path(repo_root) / "docs" / "agents" / "issue-tracker.md"
    if not path.is_file():
        return TrackerConfig("github", "gh", DEFAULT_LABELS, "builtin")

    text = path.read_text(encoding="utf-8", errors="replace")
    if "glab" in text:
        kind, cli = "gitlab", "glab"
    elif "local-markdown" in text or ".scratch" in text:
        kind, cli = "local", ""
    else:
        kind, cli = "github", "gh"

    labels = tuple(
        line.lstrip("- ").strip()
        for line in text.splitlines()
        if line.strip().startswith("- ")
        and any(word in line for word in DEFAULT_LABELS)
    )
    return TrackerConfig(
        kind,
        cli,
        labels or DEFAULT_LABELS,
        "repo",
    )
