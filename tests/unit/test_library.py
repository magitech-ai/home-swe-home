"""Tests for the per-domain experience library."""

from __future__ import annotations

import json

from magecode.library import Experience, Library, write_run_report
from magecode.utils.selection import Selection


def _experience() -> Experience:
    return Experience(
        task_id="task-1",
        cue="when scripts are repeated",
        lesson="use a script",
        evidence="candidate t2 passed where base failed",
        confidence="low",
    )


def test_empty_library(tmp_path):
    library = Library(tmp_path, "coding")
    assert library.entries() == []
    assert "empty" in library.as_prompt()


def test_add_stores_tree_and_experience(tmp_path):
    library = Library(tmp_path, "coding")
    path = library.add(
        {"systemprompt.md": "rules", "tool_guidance.md": "guide"},
        _experience(),
        Selection("cand", "highest pass rate 1.00"),
    )
    assert (path / "harness" / "systemprompt.md").read_text() == "rules"
    assert "use a script" in (path / "EXPERIENCE.md").read_text()
    assert "cand" in (path / "EXPERIENCE.md").read_text()
    assert library.entries() == ["task-1"]


def test_index_lists_entries(tmp_path):
    library = Library(tmp_path, "coding")
    library.add(
        {"systemprompt.md": "rules"}, _experience(), Selection(None, "base kept")
    )
    assert "harnesses/task-1" in library.as_prompt()


def test_domain_slash_is_neutralised(tmp_path):
    library = Library(tmp_path, "a/b")
    library.add({"systemprompt.md": "rules"}, _experience(), Selection(None, "x"))
    assert (tmp_path / "a__b" / "INDEX.md").is_file()


def test_write_run_report(tmp_path):
    path = write_run_report(
        tmp_path / "report.json",
        {"base": 0.5, "cand": 1.0},
        Selection("cand", "win"),
    )
    payload = json.loads(path.read_text())
    assert payload["winner"] == "cand"
    assert payload["scores"]["base"] == 0.5


def test_index_empty(tmp_path):
    library = Library(tmp_path, "coding")
    path = library.index()
    assert "empty" in path.read_text()
