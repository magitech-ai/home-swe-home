"""Tests for the harness A/B evaluation helper."""

from __future__ import annotations

import json
from types import SimpleNamespace

from magecode.eval import (
    BUILTIN_TASKS,
    EvalResult,
    Task,
    cli_runner,
    compare,
    evaluate,
    write_report,
)

_TASKS = (Task("a", "say a", "A"), Task("b", "say b", "B"))


def test_evaluate_counts_successes_and_failures():
    def runner(prompt, harness_dir):
        return "A" if prompt == "say a" else "nope"

    result = evaluate(_TASKS, runner)
    assert result.passes == 1
    assert result.total == 2
    assert result.failures == ("b/t1",)


def test_evaluate_multiple_trials():
    result = evaluate(_TASKS[:1], lambda *_: "A", trials=3, harness="candidate")
    assert result.passes == 3 and result.trials == 3 and result.total == 3
    assert result.harness == "candidate"


def test_pass_rate_zero_total():
    assert EvalResult("empty", 0, 0, 0, ()).pass_rate == 0.0


def test_compare_reports_delta():
    base = EvalResult("base", 1, 1, 2, ("b/t1",))
    candidate = EvalResult("candidate", 1, 2, 2, ())
    delta = compare(base, candidate)
    assert delta["delta"] == 0.5
    assert delta["base_failures"] == ["b/t1"]
    assert delta["candidate_failures"] == []


def test_write_report(tmp_path):
    result = EvalResult("base", 1, 1, 2, ("b/t1",))
    path = write_report((result,), tmp_path / "reports" / "run.json")
    payload = json.loads(path.read_text())
    assert payload[0]["pass_rate"] == 0.5
    assert payload[0]["failures"] == ["b/t1"]


def test_builtin_tasks_have_markers():
    assert len(BUILTIN_TASKS) >= 3
    assert all(task.expected and task.prompt for task in BUILTIN_TASKS)


def test_cli_runner_sets_harness_dir(tmp_path, monkeypatch):
    seen: dict[str, str] = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs["env"])
        return SimpleNamespace(stdout="out", stderr="")

    monkeypatch.setattr("magecode.eval.subprocess.run", fake_run)
    assert cli_runner("task", tmp_path) == "out"
    assert seen["MAGECODE_HARNESS_DIR"] == str(tmp_path)


def test_cli_runner_clears_harness_dir_for_base(monkeypatch):
    monkeypatch.setenv("MAGECODE_HARNESS_DIR", "/candidate")

    def fake_run(cmd, **kwargs):
        assert "MAGECODE_HARNESS_DIR" not in kwargs["env"]
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr("magecode.eval.subprocess.run", fake_run)
    cli_runner("task", None)


def test_evaluate_uses_custom_checker():
    from magecode.eval import contains_all

    tasks = (Task("custom", "do it", checker=contains_all("A", "B")),)
    assert evaluate(tasks, lambda *_: "A then B").passes == 1
    assert evaluate(tasks, lambda *_: "A only").passes == 0


def test_contains_all():
    from magecode.eval import contains_all

    assert contains_all("x", "y")("y x")
    assert not contains_all("x", "z")("y x")


def test_count_at_least():
    from magecode.eval import count_at_least

    assert count_at_least("[tool: a]", 2)("[tool: a] [tool: a]")
    assert not count_at_least("[tool: a]", 2)("[tool: a]")


def test_cli_runner_treats_timeout_as_transcript(monkeypatch):
    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            args[0], kwargs["timeout"], output=b"partial", stderr=b""
        )

    monkeypatch.setattr("magecode.eval.subprocess.run", fake_run)
    assert "[timed out]" in cli_runner("task", None)


def test_hard_tasks_are_well_formed():
    from magecode.eval import HARD_TASKS

    assert len(HARD_TASKS) == 6
    assert all(task.prompt and task.checker is not None for task in HARD_TASKS)


def test_evaluate_separates_infrastructure_errors():
    def runner(prompt, harness_dir):
        return "NVIDIA API error: 429" if prompt == "say a" else "B"

    result = evaluate(_TASKS, runner)
    assert result.total == 1
    assert result.passes == 1
    assert result.errors == ("a/t1",)
    assert result.failures == ()


def test_compare_includes_errors():
    base = EvalResult("base", 1, 0, 1, (), errors=("a/t1",))
    cand = EvalResult("cand", 1, 1, 1, ())
    assert compare(base, cand)["base_errors"] == ["a/t1"]


def test_compare_arms_interleaves_and_classifies():
    from magecode.eval import compare_arms

    order: list[str] = []

    def base(prompt, directory):
        order.append("b")
        if prompt == "say a":
            return "NVIDIA API error: 429"
        return "B"

    def candidate(prompt, directory):
        order.append("c")
        return "A" if prompt == "say a" else "B"

    b, c = compare_arms(_TASKS, base, candidate, trials=2)
    assert order == ["b", "c"] * 4
    assert b.errors == ("a/t1", "a/t2") and b.passes == 2
    assert c.passes == 4 and c.errors == ()
