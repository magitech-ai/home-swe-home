"""Tests for the harness utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from home_swe_home.utils.harness import (
    DEFAULT_HARNESS_DIR,
    harness_dir,
    read_harness,
    read_tree,
    system_prompt,
    tool_guidance,
    validate_tree,
    write_tree,
)


def test_read_tree(tmp_path: Path) -> None:
    (tmp_path / "systemprompt.md").write_text("You are helpful.", encoding="utf-8")
    tree = read_tree(tmp_path)
    assert tree == {"systemprompt.md": "You are helpful."}


def test_read_tree_empty(tmp_path: Path) -> None:
    tree = read_tree(tmp_path)
    assert tree == {}


def test_read_tree_skips_missing(tmp_path: Path) -> None:
    (tmp_path / "systemprompt.md").write_text("prompt", encoding="utf-8")
    tree = read_tree(tmp_path)
    assert "systemprompt.md" in tree
    assert "tool_guidance.md" not in tree


def test_write_tree(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    result = write_tree({"systemprompt.md": "content"}, dest)
    assert result == dest
    assert (dest / "systemprompt.md").read_text() == "content"


def test_write_tree_rejects_bad_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="off-surface"):
        write_tree({"bad.txt": "content"}, tmp_path / "out")


def test_validate_tree_valid() -> None:
    assert validate_tree({"systemprompt.md": "content"}) == ""


def test_validate_tree_bad_names() -> None:
    result = validate_tree({"bad.txt": "content"})
    assert "off-surface" in result


def test_validate_tree_empty() -> None:
    result = validate_tree({"systemprompt.md": "  "})
    assert "empty harness tree" in result


def test_harness_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_HARNESS_DIR", raising=False)
    assert harness_dir() == DEFAULT_HARNESS_DIR


def test_harness_dir_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_HARNESS_DIR", "/tmp/custom")
    assert harness_dir() == Path("/tmp/custom")


def test_read_harness_bad_name() -> None:
    with pytest.raises(ValueError, match="not an editable harness file"):
        read_harness("bad.txt")


def test_read_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "systemprompt.md").write_text("You are helpful.", encoding="utf-8")
    monkeypatch.setenv("HOME_SWE_HOME_HARNESS_DIR", str(tmp_path))
    assert read_harness("systemprompt.md") == "You are helpful."


def test_system_prompt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "systemprompt.md").write_text("Base prompt.", encoding="utf-8")
    monkeypatch.setenv("HOME_SWE_HOME_HARNESS_DIR", str(tmp_path))
    assert system_prompt() == "Base prompt."


def test_tool_guidance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    guidance = (
        "# Comments\n"
        "## read_file\n"
        "Always check the file exists first.\n"
        "\n"
        "## write_file\n"
        "Creates or overwrites.\n"
    )
    (tmp_path / "tool_guidance.md").write_text(guidance, encoding="utf-8")
    monkeypatch.setenv("HOME_SWE_HOME_HARNESS_DIR", str(tmp_path))

    assert "Always check" in tool_guidance("read_file")
    assert "Creates or overwrites" in tool_guidance("write_file")
    assert tool_guidance("unknown") == ""


def test_tool_guidance_no_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # No tool_guidance.md — should raise
    monkeypatch.setenv("HOME_SWE_HOME_HARNESS_DIR", str(tmp_path))
    with pytest.raises(OSError):
        tool_guidance("read_file")
