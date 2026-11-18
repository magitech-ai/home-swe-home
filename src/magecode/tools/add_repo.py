"""Resolve a repo from the home map and clone it on confirmation."""

from __future__ import annotations

import subprocess

from anima import Context, Service

from ..utils.home import find_home
from ..utils.repo_map import parse_repo_map, resolve_repo


class AddRepoService(Service):
    """Mounted as ``ctx.add_repo`` and exposed as a model tool."""

    def __init__(self, ctx: Context):
        super().__init__(ctx, "add_repo")

    def __call__(self, *, ref: str, confirm: bool = False) -> str:
        """Resolve a repo name, clone URL or local directory from the home map.

        Args:
            ref: Repo name, GitHub URL, or relative path from the home map.
            confirm: Set true to actually clone a missing checkout.
        """
        home = find_home()
        if home is None:
            return "Error: no agents-home checkout is configured."
        entries = parse_repo_map((home / "AGENTS.md").read_text(encoding="utf-8"))
        entry = resolve_repo(entries, ref)
        if entry is None:
            return f"Error: '{ref}' is not in the home repo map."

        target = (home / entry.path).resolve()
        if target.is_dir():
            return f"Resolved '{entry.name}' to {target}."

        if not entry.clone_url:
            return f"Error: '{entry.name}' has no clone URL in the map."
        if not confirm:
            return (
                f"Confirm with confirm=true to clone '{entry.name}' from "
                f"{entry.clone_url} into {target}."
            )

        result = subprocess.run(  # noqa: S603 - fixed command shape
            ["git", "clone", entry.clone_url, str(target)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return f"Error: clone failed: {result.stderr.strip()[:300]}"
        return f"Cloned '{entry.name}' into {target}."
