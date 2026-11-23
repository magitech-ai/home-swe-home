"""Tests for the evidence-based CI wait used by the review workflow."""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wait_for_ci  # noqa: E402


def _check(name: str, bucket: str) -> dict:
    return {"name": name, "state": "COMPLETED", "bucket": bucket, "link": "https://ci"}


def test_classify_no_matching_checks_is_pending() -> None:
    state, details = wait_for_ci.classify(
        [_check("Agent review", "pending")], "Test & Lint"
    )
    assert (state, details) == ("pending", [])


def test_classify_failure_wins_over_pending() -> None:
    checks = [
        _check("Test & Lint / ci (ubuntu)", "fail"),
        _check("Test & Lint / ci (macos)", "pending"),
    ]
    state, details = wait_for_ci.classify(checks, "Test & Lint")
    assert state == "fail"
    assert len(details) == 2


def test_classify_all_passing_is_pass() -> None:
    checks = [
        _check("Test & Lint / ci (ubuntu)", "pass"),
        _check("Test & Lint / ci (macos)", "pass"),
    ]
    state, _ = wait_for_ci.classify(checks, "Test & Lint")
    assert state == "pass"


def test_classify_unknown_bucket_is_pending() -> None:
    state, details = wait_for_ci.classify(
        [_check("Test & Lint / ci", "queued")], "Test & Lint"
    )
    assert state == "pending"
    assert details[0]["bucket"] == "queued"


def test_fetch_empty_output_is_pending_input() -> None:
    with patch.object(wait_for_ci.subprocess, "run") as run:
        run.return_value.stdout = ""
        assert wait_for_ci.fetch("org/repo", 7) == []


def test_fetch_parses_github_rollup() -> None:
    rollup = [_check("Test & Lint / ci", "pass")]
    with patch.object(wait_for_ci.subprocess, "run") as run:
        run.return_value.stdout = json.dumps(rollup)
        assert wait_for_ci.fetch("org/repo", 7) == rollup


def test_main_waits_through_pending_then_passes() -> None:
    pending = [_check("Test & Lint / ci", "pending")]
    passing = [_check("Test & Lint / ci", "pass")]
    with (
        patch.object(wait_for_ci, "fetch", side_effect=[pending, passing]),
        patch.object(wait_for_ci.time, "monotonic", side_effect=[0, 1]),
        patch.object(wait_for_ci.time, "sleep") as sleep,
        redirect_stdout(io.StringIO()) as out,
    ):
        rc = wait_for_ci.main(["--repo", "org/repo", "--pr", "7", "--timeout", "10"])
    assert rc == 0
    sleep.assert_called_once_with(15)
    assert "CI checks: pending" in out.getvalue()
    assert "CI checks: pass" in out.getvalue()


def test_main_fails_immediately_on_ci_failure() -> None:
    failing = [_check("Test & Lint / ci", "fail")]
    with (
        patch.object(wait_for_ci, "fetch", return_value=failing),
        redirect_stdout(io.StringIO()),
    ):
        rc = wait_for_ci.main(["--repo", "org/repo", "--pr", "7"])
    assert rc == 1


def test_main_times_out_without_claiming_a_pass() -> None:
    pending = [_check("Test & Lint / ci", "pending")]
    with (
        patch.object(wait_for_ci, "fetch", return_value=pending),
        patch.object(wait_for_ci.time, "monotonic", side_effect=[0, 0]),
        patch.object(wait_for_ci.time, "sleep"),
        redirect_stdout(io.StringIO()),
    ):
        rc = wait_for_ci.main(["--repo", "org/repo", "--pr", "7", "--timeout", "0"])
    assert rc == 2
