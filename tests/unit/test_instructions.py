"""Tests for the instructions module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from home_swe_home.instructions import (
    agents_md,
    base_instructions,
    system_line,
)


def test_system_line_defaults() -> None:
    result = system_line()
    assert "System:" in result
    assert "folder:" in result
    assert "date:" in result
    assert "model:" in result


def test_system_line_with_args() -> None:
    result = system_line(model="test-model", cwd="/tmp/test")
    assert "test-model" in result
    assert "/tmp/test" in result


def test_system_line_no_model() -> None:
    result = system_line()
    assert "unknown" in result


def test_agents_md_no_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("home_swe_home.utils.home.find_home", lambda: None)
    with patch("os.getcwd", return_value="/tmp/nonexistent"):
        result = agents_md()
    # No AGENTS.md found, should return empty string
    assert isinstance(result, str)


def test_agents_md_with_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text("Home guidance here.", encoding="utf-8")
    monkeypatch.setattr("home_swe_home.utils.home.find_home", lambda: home)

    with patch("os.getcwd", return_value=str(tmp_path)):
        result = agents_md()

    assert "Home guidance here." in result
    assert "AGENTS.md" in result


def test_agents_md_deduplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text("Same content.", encoding="utf-8")
    monkeypatch.setattr("home_swe_home.utils.home.find_home", lambda: home)

    # Run from the home directory — should not duplicate
    with patch("os.getcwd", return_value=str(home)):
        result = agents_md()

    # Should appear only once
    assert result.count("Same content.") == 1


def test_agents_md_empty_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text("   ", encoding="utf-8")
    monkeypatch.setattr("home_swe_home.utils.home.find_home", lambda: home)

    with patch("os.getcwd", return_value=str(tmp_path)):
        result = agents_md()

    # Whitespace-only file should not be included
    assert "AGENTS.md" not in result


def test_base_instructions_reads_harness(monkeypatch, tmp_path):
    """The live prompt comes from the editable harness tree."""
    (tmp_path / "systemprompt.md").write_text("From harness.", encoding="utf-8")
    monkeypatch.setenv("HOME_SWE_HOME_HARNESS_DIR", str(tmp_path))
    assert base_instructions() == "From harness."


def test_base_instructions_falls_back(monkeypatch, tmp_path):
    """A missing harness file falls back to a built-in prompt."""
    monkeypatch.setenv("HOME_SWE_HOME_HARNESS_DIR", str(tmp_path))
    assert "coding agent" in base_instructions()
