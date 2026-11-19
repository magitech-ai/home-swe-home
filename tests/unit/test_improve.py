"""Tests for the external improvement step."""

from __future__ import annotations

from pathlib import Path

import pytest

from home_swe_home.improve import StepResult, default_runner, run_step
from home_swe_home.utils.harness import (
    DEFAULT_HARNESS_DIR,
    read_tree,
    validate_tree,
    write_tree,
)


def test_read_tree_from_packaged_harness():
    tree = read_tree(DEFAULT_HARNESS_DIR)
    assert "systemprompt.md" in tree
    assert "tool_guidance.md" in tree


def test_read_tree_missing_files(tmp_path):
    assert read_tree(tmp_path) == {}


def test_write_tree_rejects_off_surface(tmp_path):
    with pytest.raises(ValueError, match="off-surface"):
        write_tree({"evil.txt": "x"}, tmp_path / "out")


def test_write_tree_materialises_files(tmp_path):
    out = write_tree({"systemprompt.md": "new rules"}, tmp_path / "out")
    assert (out / "systemprompt.md").read_text() == "new rules"


def test_validate_tree_rejects_off_surface():
    assert "off-surface" in validate_tree({"bad.md": "x"})


def test_validate_tree_rejects_empty():
    assert "empty" in validate_tree({"systemprompt.md": "   "})


def test_validate_tree_accepts_valid():
    assert validate_tree({"systemprompt.md": "rules"}) == ""


def test_run_step_proposes_validates_and_probes(tmp_path):
    def propose(task, base):
        assert task == "do the thing"
        assert "systemprompt.md" in base
        return {**base, "tool_guidance.md": "## tdd\nAlways test.\n"}

    calls: list[Path] = []

    def run(candidate, task):
        calls.append(candidate)
        return "probe output"

    result = run_step(
        base_dir=DEFAULT_HARNESS_DIR,
        work_dir=tmp_path,
        task="do the thing",
        propose=propose,
        run=run,
    )
    assert result.accepted and result.rollout == "probe output"
    assert calls == [result.candidate]
    assert "Always test." in (result.candidate / "tool_guidance.md").read_text()  # type: ignore[union-attr]


def test_run_step_rejects_invalid_candidate_without_probing(tmp_path):
    def propose(task, base):
        return {"bad.md": "nope"}

    def run(candidate, task):
        raise AssertionError("must not probe an invalid tree")

    result = run_step(
        base_dir=DEFAULT_HARNESS_DIR,
        work_dir=tmp_path,
        task="task",
        propose=propose,
        run=run,
    )
    assert not result.accepted and "off-surface" in result.error
    assert result.candidate is None and result.rollout == ""


def test_default_runner_passes_candidate_in_env(tmp_path, monkeypatch):
    seen: dict[str, str] = {}

    class Completed:
        stdout = "out"
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen.update(kwargs["env"])
        return Completed()

    monkeypatch.setattr("home_swe_home.improve.subprocess.run", fake_run)
    assert default_runner(tmp_path / "candidate", "task") == "out"
    assert seen["HOME_SWE_HOME_HARNESS_DIR"] == str(tmp_path / "candidate")


def test_step_result_is_frozen():
    result = StepResult(True, "", None, "")
    with pytest.raises(Exception):
        result.accepted = False  # type: ignore[misc]
