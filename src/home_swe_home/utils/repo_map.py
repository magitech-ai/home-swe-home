"""Parse the curated repository map in the home ``AGENTS.md``.

The map is the home repo's source of truth for sibling checkout paths and
clone URLs. Parsing it keeps home-swe-home from duplicating that list in code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADER = "## Other Repos"
_NAME = re.compile(r"^- \*\*(.+?)\*\*")
_PATH = re.compile(r"\]\((\.{1,2}/[^)]+)\)|`(\.{1,2}/[^`]+)`")
_URL = re.compile(r"<(https://github\.com/[^>]+)>")


@dataclass(frozen=True)
class RepoEntry:
    """One mapped repository: display name, path relative to home, clone URL."""

    name: str
    path: str
    clone_url: str = ""


def parse_repo_map(text: str) -> list[RepoEntry]:
    """Return the entries under ``## Other Repos``, or an empty list.

    Continuation lines are folded into their bullet so entries spanning
    several lines parse identically to single-line ones.
    """
    lines = text.splitlines()
    if _HEADER not in lines:
        return []
    start = lines.index(_HEADER) + 1
    groups: list[list[str]] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if _NAME.match(line):
            groups.append([line])
        elif groups and line.strip():
            groups[-1].append(line.strip())

    entries: list[RepoEntry] = []
    for group in groups:
        joined = " ".join(part.strip() for part in group)
        name = _NAME.match(joined)
        path = _PATH.search(joined)
        if name is None or path is None:
            continue
        url = _URL.search(joined)
        entries.append(
            RepoEntry(
                name=name.group(1).strip(),
                path=(path.group(1) or path.group(2)).rstrip("/"),
                clone_url=url.group(1) if url else "",
            )
        )
    return entries


def resolve_repo(entries: list[RepoEntry], ref: str) -> RepoEntry | None:
    """Resolve a name, clone URL or relative path to one mapped entry."""
    wanted = ref.strip().rstrip("/")
    for entry in entries:
        if entry.name.casefold() == wanted.casefold():
            return entry
    for entry in entries:
        if entry.clone_url and entry.clone_url.removesuffix(
            ".git"
        ) == wanted.removesuffix(".git"):
            return entry
    for entry in entries:
        if entry.path == wanted:
            return entry
    return None
