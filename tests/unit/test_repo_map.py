"""Tests for the curated repository map parser."""

from __future__ import annotations

from home_swe_home.utils.repo_map import RepoEntry, parse_repo_map, resolve_repo

_MAP = """\
# Agents Home

Some preamble.

## Other Repos

- **Organization defaults**: [`.github`](../.github/). Consult its docs.
- **animas** (async kernel): `../animas`. Clone from
  <https://github.com/magitech-ai/animas.git> if missing. Read its
  `AGENTS.md` before changes.
- **broken entry** with no usable path.
- **home-swe-home** (agent): `../home-swe-home`. Clone from
  <https://github.com/magitech-ai/home-swe-home.git> if missing.

## Plans

- not part of the map
"""


def test_parse_repo_map_missing_header():
    assert parse_repo_map("# Other text\n") == []


def test_parse_repo_map_stops_at_next_section():
    entries = parse_repo_map(_MAP)
    assert [entry.name for entry in entries] == [
        "Organization defaults",
        "animas",
        "home-swe-home",
    ]


def test_parse_repo_map_markdown_link_path_and_no_url():
    entries = parse_repo_map(_MAP)
    assert entries[0].path == "../.github"
    assert entries[0].clone_url == ""


def test_parse_repo_map_folds_continuation_lines():
    animas = parse_repo_map(_MAP)[1]
    assert animas.path == "../animas"
    assert animas.clone_url == "https://github.com/magitech-ai/animas.git"


def test_parse_repo_map_at_end_of_document():
    text = "## Other Repos\n\n- **animas**: `../animas`.\n"
    assert [entry.name for entry in parse_repo_map(text)] == ["animas"]


def test_parse_repo_map_empty_section():
    assert parse_repo_map("## Other Repos\n\n## Plans\n") == []


def test_resolve_repo_by_name_case_insensitive():
    entries = parse_repo_map(_MAP)
    assert resolve_repo(entries, " ANIMAS ") == entries[1]


def test_resolve_repo_by_url_with_and_without_git_suffix():
    entries = parse_repo_map(_MAP)
    url = "https://github.com/magitech-ai/animas"
    assert resolve_repo(entries, url + ".git") == entries[1]
    assert resolve_repo(entries, url) == entries[1]


def test_resolve_repo_by_path():
    entries = parse_repo_map(_MAP)
    assert resolve_repo(entries, "../home-swe-home/") == entries[2]


def test_resolve_repo_ignores_empty_clone_url():
    entries = parse_repo_map(_MAP)
    assert resolve_repo(entries, "../.github") == entries[0]


def test_resolve_repo_unknown():
    entries = [RepoEntry("animas", "../animas")]
    assert resolve_repo(entries, "nope") is None


def test_uses_the_canonical_mth_plugins_parser():
    from mth_plugins.tools.dev_tools.repo_map import parse_repo_map as canonical

    assert parse_repo_map is canonical
