"""Tests for mechanical validation of reviewer evidence citations."""

from __future__ import annotations

from pathlib import Path

from home_swe_home.evidence import check_finding_evidence
from home_swe_home.review import Finding

DIFF = (
    "diff --git a/src/demo.py b/src/demo.py\n"
    "--- a/src/demo.py\n"
    "+++ b/src/demo.py\n"
    "@@ -1 +1 @@\n-old\n+new\n"
)


def finding(evidence: str) -> Finding:
    return Finding(severity="major", evidence=evidence, message="m")


def check(evidence: str, root: Path | None = None) -> str:
    results = check_finding_evidence(
        [finding(evidence)], diff=DIFF, root=root or Path.cwd()
    )
    return results[0].status


def test_citation_to_diff_path() -> None:
    assert check("src/demo.py:1-3") == "diff"


def test_citation_to_existing_repo_file(tmp_path) -> None:
    (tmp_path / "notes.md").write_text("x", encoding="utf-8")
    assert check("notes.md:4", root=tmp_path) == "repo"


def test_citation_to_documented_rule() -> None:
    assert check("Standard: REVIEW (Non-negotiables 3)") == "rule"
    assert check("Acceptance criteria: add a test") == "rule"


def test_citation_to_missing_path_is_unverifiable(tmp_path) -> None:
    assert check("src/does_not_exist.py:12", root=tmp_path) == "unverifiable"


def test_citation_without_path_is_unverifiable(tmp_path) -> None:
    assert check("the code clearly looks wrong", root=tmp_path) == "unverifiable"


def test_malformed_diff_header_is_ignored() -> None:
    diff = "diff --git a/x.py\n+++ b/x.py\n@@ -0,0 +1 @@\n+x\n"
    results = check_finding_evidence(
        [finding("x.py:1")], diff=diff, root=Path("/nonexistent")
    )
    assert results[0].status == "diff"


def test_diff_paths_from_git_header() -> None:
    diff = "diff --git a/a.py b/b.py\n--- a/a.py\n+++ b/b.py\n@@ -0,0 +1 @@\n+x\n"
    results = check_finding_evidence(
        [finding("b.py:1")], diff=diff, root=Path("/nonexistent")
    )
    assert results[0].status == "diff"
