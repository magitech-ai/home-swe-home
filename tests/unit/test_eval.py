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
