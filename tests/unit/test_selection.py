"""Tests for candidate selection and composition."""

from __future__ import annotations

from magecode.utils.selection import compose, select


def test_select_empty():
    result = select({})
    assert result.winner is None
    assert "no candidates" in result.reason


def test_select_base_wins():
    assert select({"base": 1.0, "cand": 0.5}).winner is None


def test_select_tie_keeps_base():
    assert select({"a": 0.8, "b": 0.8}).winner is None


def test_select_strict_winner():
    result = select({"base": 0.8, "cand": 1.0})
    assert result.winner == "cand"
    assert "1.00" in result.reason


def test_compose_without_candidates():
    base = {"systemprompt.md": "base"}
    assert compose(base, {}, {}) == base


def test_compose_applies_changed_file_from_best_candidate():
    base = {"systemprompt.md": "base", "tool_guidance.md": "guide"}
    candidates = {
        "low": {"systemprompt.md": "low change", "tool_guidance.md": "guide"},
        "high": {"systemprompt.md": "high change", "tool_guidance.md": "guide"},
    }
    result = compose(base, candidates, {"low": 0.4, "high": 0.9})
    assert result["systemprompt.md"] == "high change"
    assert result["tool_guidance.md"] == "guide"


def test_compose_keeps_base_file_when_no_candidate_changes_it():
    base = {"systemprompt.md": "base", "tool_guidance.md": "guide"}
    candidates = {"a": {"systemprompt.md": "changed"}}
    result = compose(base, candidates, {"a": 1.0})
    assert result["tool_guidance.md"] == "guide"


def test_compose_tie_prefers_alphabetically_first():
    base = {"systemprompt.md": "base"}
    candidates = {"b": {"systemprompt.md": "B"}, "a": {"systemprompt.md": "A"}}
    assert compose(base, candidates, {"a": 0.5, "b": 0.5})["systemprompt.md"] == "A"
