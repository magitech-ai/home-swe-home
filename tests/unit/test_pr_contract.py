"""Tests for the deterministic PR-contract pre-flight."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pr_contract  # noqa: E402


def test_parse_trigger_issue_handles_bullet_and_plain_forms() -> None:
    assert pr_contract.parse_trigger_issue("Trigger issue: #140\n") == 140
    assert pr_contract.parse_trigger_issue("- Trigger issue: #138 —") == 138
    assert pr_contract.parse_trigger_issue("no issue here") is None


def test_named_paths_ignores_bare_words_and_cleans_punctuation() -> None:
    paths = pr_contract.named_paths(
        "Update `scripts/wait_for_ci.py`, `docs/agents/review-standard.md`.\n"
        "Coverage is 100%. See src/home_swe_home/gate.py."
    )
    assert "scripts/wait_for_ci.py" in paths
    assert "docs/agents/review-standard.md" in paths
    assert "src/home_swe_home/gate.py" in paths
    assert "Coverage" not in paths


def test_check_passes_for_open_issue_with_matching_path() -> None:
    problems = pr_contract.check(
        pr_body="Trigger issue: #140\n",
        issue_state="OPEN",
        issue_body="## Goal\nChange `scripts/wait_for_ci.py`.\n",
        changed_files=["scripts/wait_for_ci.py"],
        expected_issue=140,
    )
    assert problems == []


def test_check_rejects_closed_issue_and_mismatched_number() -> None:
    problems = pr_contract.check(
        pr_body="Trigger issue: #140\n",
        issue_state="CLOSED",
        issue_body="## Goal\nDo a thing.\n",
        changed_files=["src/a.py"],
        expected_issue=141,
    )
    assert any("CLOSED" in p for p in problems)
    assert any("#140" in p and "#141" in p for p in problems)


def test_check_rejects_scope_mismatch_when_issue_names_paths() -> None:
    problems = pr_contract.check(
        pr_body="Trigger issue: #1\n",
        issue_state="OPEN",
        issue_body="Change `src/home_swe_home/gate.py` only.\n",
        changed_files=["docs/README.md"],
    )
    assert any("none are in the diff" in p for p in problems)


def test_check_allows_issue_without_named_paths() -> None:
    problems = pr_contract.check(
        pr_body="Trigger issue: #1\n",
        issue_state="OPEN",
        issue_body="## Goal\nMake the reviewer wait for CI.\n",
        changed_files=["docs/README.md"],
    )
    assert problems == []


def test_check_rejects_empty_issue_body() -> None:
    problems = pr_contract.check(
        pr_body="Trigger issue: #1\n",
        issue_state="OPEN",
        issue_body="  \n",
        changed_files=[],
    )
    assert any("no body" in p for p in problems)


def test_main_reports_fetch_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pr_body = tmp_path / "pr.txt"
    pr_body.write_text("Trigger issue: #1\n", encoding="utf-8")
    changed = tmp_path / "files.txt"
    changed.write_text("src/a.py\n", encoding="utf-8")

    def boom(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, "", "not found")

    monkeypatch.setattr(pr_contract.subprocess, "run", boom)
    rc = pr_contract.main(
        [
            "--repo",
            "o/r",
            "--issue",
            "1",
            "--pr-body-file",
            str(pr_body),
            "--changed-files-file",
            str(changed),
        ]
    )
    assert rc == 2


def test_main_reports_contract_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pr_body = tmp_path / "pr.txt"
    pr_body.write_text("nothing here\n", encoding="utf-8")
    changed = tmp_path / "files.txt"
    changed.write_text("src/a.py\n", encoding="utf-8")
    monkeypatch.setattr(pr_contract, "fetch_issue", lambda r, i: ("OPEN", "goal"))
    rc = pr_contract.main(
        [
            "--repo",
            "o/r",
            "--issue",
            "1",
            "--pr-body-file",
            str(pr_body),
            "--changed-files-file",
            str(changed),
        ]
    )
    assert rc == 1


def test_main_returns_zero_on_valid_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pr_body = tmp_path / "pr.txt"
    pr_body.write_text("Trigger issue: #1\n", encoding="utf-8")
    changed = tmp_path / "files.txt"
    changed.write_text("src/a.py\n", encoding="utf-8")
    monkeypatch.setattr(pr_contract, "fetch_issue", lambda r, i: ("OPEN", "goal"))
    rc = pr_contract.main(
        [
            "--repo",
            "o/r",
            "--issue",
            "1",
            "--pr-body-file",
            str(pr_body),
            "--changed-files-file",
            str(changed),
        ]
    )
    assert rc == 0
