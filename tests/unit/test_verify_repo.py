"""Tests for the verify_repo tool definition."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from home_swe_home.tools.definitions import VERIFY_REPO


def test_verify_repo_runs_default_checks(tmp_path: Path) -> None:
    calls: list[tuple[str, object]] = []

    def fake_runner(command: str, cwd: Path) -> tuple[int, str]:
        calls.append((command, cwd))
        return (0, "")

    with patch(
        "home_swe_home.utils.verify.default_runner", side_effect=fake_runner
    ):
        result = VERIFY_REPO["execute"](
            {"path": str(tmp_path)}, {"signal": None, "agent": None}
        )

    assert "4/4 checks passed" in result
    assert len(calls) == 4


def test_verify_repo_reports_failures(tmp_path: Path) -> None:
    def fake_runner(command: str, cwd: Path) -> tuple[int, str]:
        if "ruff" in command:
            return (1, "E501 line too long")
        return (0, "")

    with patch(
        "home_swe_home.utils.verify.default_runner", side_effect=fake_runner
    ):
        result = VERIFY_REPO["execute"](
            {"path": str(tmp_path)}, {"signal": None, "agent": None}
        )

    assert "FAIL" in result
    assert "3/4 checks passed" in result
    assert "E501" in result