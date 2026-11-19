"""Tests for a full improvement cycle."""

from __future__ import annotations

from home_swe_home.improve import CycleResult, run_cycle
from home_swe_home.utils.harness import DEFAULT_HARNESS_DIR, read_tree


def test_cycle_scores_selects_and_composes(tmp_path):
    candidates = {
        "bad": {"systemprompt.md": "bad rules"},
        "good": {"systemprompt.md": "good rules"},
    }
    result = run_cycle(
        base_dir=DEFAULT_HARNESS_DIR,
        work_dir=tmp_path,
        tasks=("task",),
        candidates=candidates,
        evaluate_fn=lambda directory, tasks: 1.0 if "good" in str(directory) else 0.0,
    )
    assert isinstance(result, CycleResult)
    assert result.scores == {"bad": 0.0, "good": 1.0}
    assert result.selection.winner == "good"  # type: ignore[union-attr]
    assert result.final["systemprompt.md"] == "good rules"
    assert read_tree(result.final_dir)["systemprompt.md"] == "good rules"


def test_cycle_skips_invalid_candidates(tmp_path):
    result = run_cycle(
        base_dir=DEFAULT_HARNESS_DIR,
        work_dir=tmp_path,
        tasks=(),
        candidates={"broken": {"evil.txt": "x"}},
        evaluate_fn=lambda directory, tasks: 1.0,
    )
    assert result.scores == {}
    assert result.selection.winner is None  # type: ignore[union-attr]
    assert result.final == read_tree(DEFAULT_HARNESS_DIR)
