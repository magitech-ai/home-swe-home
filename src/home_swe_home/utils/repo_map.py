"""Compatibility re-export of the canonical repo-map parser.

The single implementation lives in ``mth_components.tools.dev_tools.repo_map``.
home-swe-home imports it so there is one parser for the home ``AGENTS.md``
curated map, shared with the mth-components ``add_repo`` tool.
"""

from __future__ import annotations

from mth_components.tools.dev_tools.repo_map import (
    RepoEntry,
    parse_repo_map,
    resolve_repo,
)

__all__ = ["RepoEntry", "parse_repo_map", "resolve_repo"]
