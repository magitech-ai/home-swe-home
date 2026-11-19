"""Per-domain experience library for adopted harnesses and their lessons."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .utils.harness import write_tree
from .utils.selection import Selection


@dataclass(frozen=True)
class Experience:
    """The evidence-backed lesson attached to one adopted harness."""

    task_id: str
    cue: str
    lesson: str
    evidence: str
    confidence: str


class Library:
    """A directory of prior tasks in one domain, read before future edits."""

    def __init__(self, root: Path, domain: str) -> None:
        self.root = Path(root) / domain.replace("/", "__")
        self.domain = domain

    def entries(self) -> list[str]:
        """List stored task ids in stable order."""
        directory = self.root / "harnesses"
        return (
            sorted(p.name for p in directory.iterdir() if p.is_dir())
            if directory.is_dir()
            else []
        )

    def add(
        self,
        harness: dict[str, str],
        experience: Experience,
        selection: Selection,
    ) -> Path:
        """Store the full adopted tree plus its why, then rebuild the index."""
        destination = self.root / "harnesses" / experience.task_id.replace("/", "__")
        write_tree(harness, destination / "harness")
        (destination / "EXPERIENCE.md").write_text(
            "\n".join(
                [
                    f"# {experience.task_id}",
                    "",
                    f"- adopted: `{selection.winner or 'base'}`",
                    f"- reason: {selection.reason}",
                    "",
                    "## Transferable lesson",
                    f"- **cue**: {experience.cue}",
                    f"- **lesson**: {experience.lesson}",
                    f"- **evidence**: {experience.evidence}",
                    f"- **confidence**: {experience.confidence}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.index()
        return destination

    def index(self) -> Path:
        """Regenerate and return INDEX.md from what is on disk."""
        lines = [f"# Library — {self.domain}", ""]
        entries = self.entries()
        if not entries:
            lines.append("_(empty — this is the first task in this domain)_")
        for entry in entries:
            lines += [
                f"## `harnesses/{entry}/`",
                "- harness: `harness/harness/`",
                "- why: `EXPERIENCE.md`",
                "",
            ]
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "INDEX.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def as_prompt(self) -> str:
        """Return the index text for serving to an improver."""
        path = self.root / "INDEX.md"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return (
            f"# Library — {self.domain}\n\n"
            "_(empty — this is the first task in this domain)_\n"
        )


def write_run_report(
    path: Path, scores: dict[str, float], selection: Selection
) -> Path:
    """Persist a cycle's measured scores and decision as JSON."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scores": scores,
        "winner": selection.winner,
        "reason": selection.reason,
    }
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination
