"""Pure helpers for magecode's editable harness tree.

The harness is the part of magecode that is data rather than code: the base
system prompt and per-tool guidance. An improvement loop can roll out a
candidate tree by pointing ``MAGECODE_HARNESS_DIR`` at a copy; Services read
the active tree when a session starts.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HARNESS_DIR = Path(__file__).resolve().parents[1] / "harness"
_EDITABLE = frozenset({"systemprompt.md", "tool_guidance.md"})


def read_tree(root: Path) -> dict[str, str]:
    """Read every editable harness file present under *root*."""
    tree: dict[str, str] = {}
    for name in sorted(_EDITABLE):
        path = Path(root) / name
        if path.is_file():
            tree[name] = path.read_text(encoding="utf-8")
    return tree


def write_tree(tree: dict[str, str], dest: Path) -> Path:
    """Materialise a candidate tree, rejecting off-surface filenames."""
    bad = sorted(set(tree) - _EDITABLE)
    if bad:
        raise ValueError(f"off-surface harness files: {', '.join(bad)}")
    destination = Path(dest)
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in tree.items():
        (destination / name).write_text(content, encoding="utf-8")
    return destination


def validate_tree(tree: dict[str, str]) -> str:
    """Return an error string for an invalid tree, or ``''`` when valid."""
    bad = sorted(set(tree) - _EDITABLE)
    if bad:
        return f"off-surface harness files: {', '.join(bad)}"
    if not any(value.strip() for value in tree.values()):
        return "empty harness tree"
    return ""


def harness_dir() -> Path:
    """Return the active harness directory (env override for candidate trees)."""
    override = os.environ.get("MAGECODE_HARNESS_DIR")
    return Path(override) if override else DEFAULT_HARNESS_DIR


def read_harness(name: str) -> str:
    """Read one editable harness file, rejecting names outside the tree."""
    if name not in _EDITABLE:
        raise ValueError(f"not an editable harness file: {name!r}")
    return (harness_dir() / name).read_text(encoding="utf-8")


def system_prompt() -> str:
    """Return the base system prompt from the harness tree."""
    return read_harness("systemprompt.md")


def tool_guidance(name: str) -> str:
    """Return the guidance section for tool *name*, or ``''`` if it has none.

    Sections are ``## <tool_name>`` headings; their body is appended to that
    tool's model-facing description. Lines beginning with ``#`` are comments.
    """
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in read_harness("tool_guidance.md").splitlines():
        if line.startswith("## "):
            current = sections.setdefault(line[3:].strip(), [])
        elif current is not None and not line.lstrip().startswith("#"):
            current.append(line)
    return "\n".join(sections.get(name, [])).strip()
