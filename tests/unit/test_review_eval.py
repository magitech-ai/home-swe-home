"""Hermetic tests for the Stage B injected-defect harness."""

from __future__ import annotations

import json
from types import SimpleNamespace

from home_swe_home import review_eval
from home_swe_home.review import ReviewOutcome, Verdict

PERFECT = Verdict(verdict="APPROVE", summary="ok", findings=[])
CHANGED = Verdict(verdict="REQUEST_CHANGES", summary="not ok", findings=[])


def test_case_suite_meets_d012_structure() -> None:
    assert len(review_eval.CASES) >= 15
    assert sum(c.has_defect for c in review_eval.CASES) >= 3
    assert sum(not c.has_defect for c in review_eval.CASES) >= 3
    assert (
        sum(
            c.has_defect and c.category == "contract_fidelity"
            for c in review_eval.CASES
        )
        >= 3
    )
    assert sum(c.id.startswith("real-") for c in review_eval.CASES) >= 8
    assert sum(c.category == "injection" for c in review_eval.CASES) >= 4


def test_evaluate_runs_every_case(monkeypatch) -> None:
    # Synthetic cases: real case specs can appear inside real PR diffs used by
    # scale cases, which would make a spec-matching fake ambiguous.
    cases = (
        review_eval.Case("synthetic-bad", "unit", "Do X", "diff", True, "X"),
        review_eval.Case("synthetic-good", "unit", "Do Y", "diff", False, ""),
    )

    def fake_run(_client, *, model, user_prompt, reasoning_effort=None):
        assert model == "reviewer"
        for case in cases:
            if case.spec in user_prompt:
                return ReviewOutcome(CHANGED if case.has_defect else PERFECT, 10, 5)
        raise AssertionError("prompt did not contain a known case spec")

    monkeypatch.setattr(review_eval, "run_review_with_usage", fake_run)
    results = review_eval.evaluate(SimpleNamespace(), model="reviewer", cases=cases)
    assert len(results) == len(cases)
    assert all(r.verdict.approved == (not r.case.has_defect) for r in results)


def result(case, approved: bool) -> review_eval.Result:
    return review_eval.Result(case, PERFECT if approved else CHANGED, 1.0)


def test_summarize_perfect_run() -> None:
    summary = review_eval.summarize(
        [result(c, approved=not c.has_defect) for c in review_eval.CASES]
    )
    assert summary["detection_rate"] == 1.0
    assert summary["false_approves"] == []
    assert summary["false_positives"] == []
    assert summary["contract_false_approves"] == []
    assert summary["injection_false_approves"] == []
    assert summary["injection_cases"] >= 4
    assert summary["real_derived_cases"] >= 8
    assert summary["avg_seconds"] == 1.0


def test_summarize_reports_misses_and_false_positives() -> None:
    cases = review_eval.CASES
    results = [result(c, approved=not c.has_defect) for c in cases]
    missed = next(c for c in cases if c.category == "contract_fidelity")
    injected = next(c for c in cases if c.category == "injection")
    clean = next(c for c in cases if not c.has_defect)
    results[cases.index(missed)] = result(missed, approved=True)
    results[cases.index(injected)] = result(injected, approved=True)
    results[cases.index(clean)] = result(clean, approved=False)
    summary = review_eval.summarize(results)
    assert missed.id in summary["false_approves"]
    assert missed.id in summary["contract_false_approves"]
    assert clean.id in summary["false_positives"]
    assert injected.id in summary["injection_false_approves"]
    assert summary["detection_rate"] < 1.0


def test_summarize_empty_is_safe() -> None:
    summary = review_eval.summarize([])
    assert summary["detection_rate"] == 0.0
    assert summary["false_positive_rate"] == 0.0
    assert summary["avg_seconds"] == 0.0


def test_main_writes_results(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        review_eval, "config_for", lambda _p: ("https://x.invalid", "k", "Fake")
    )
    monkeypatch.setattr(review_eval, "load_dotenv", lambda: None)
    monkeypatch.setattr(review_eval, "OpenAI", lambda **_kw: SimpleNamespace())
    monkeypatch.setattr(
        review_eval,
        "evaluate",
        lambda _client, *, model, reasoning_effort=None: [
            result(review_eval.CASES[0], approved=False)
        ],
    )
    out = tmp_path / "results.json"
    code = review_eval.main(["--provider", "fake", "--model", "m", "--out", str(out)])
    assert code == 0
    payload = json.loads(out.read_text())
    assert payload["model"] == "m"
    assert payload["results"][0]["verdict"] == "REQUEST_CHANGES"


def test_main_fails_closed_on_config_error(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(review_eval, "load_dotenv", lambda: None)

    def bad(_provider):
        raise ValueError("bad provider")

    monkeypatch.setattr(review_eval, "config_for", bad)
    code = review_eval.main(
        ["--provider", "bad", "--model", "m", "--out", str(tmp_path / "x.json")]
    )
    assert code == 2
    assert "bad provider" in capsys.readouterr().err
