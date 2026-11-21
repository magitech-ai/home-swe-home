"""Tests for the Propose–Probe–Compose improvement orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from home_swe_home.eval import EvalResult, Task
from home_swe_home.orchestrate import (
    ProposalError,
    _validate_candidate,
    build_proposer,
    default_ask,
    run_cycle,
)

BASE_TREE = {
    "systemprompt.md": "You are a coding agent.",
    "tool_guidance.md": "## read_file\nRead a file.",
}


def _task(task_id: str = "t1") -> Task:
    return Task(id=task_id, prompt="do something", checker=lambda _t: True)


def _result(harness: str, passes: int, total: int) -> EvalResult:
    return EvalResult(
        harness=harness, trials=1, passes=passes, total=total, failures=()
    )


def _make_base(tmp_path: Path) -> Path:
    base = tmp_path / "base"
    base.mkdir()
    for name, text in BASE_TREE.items():
        (base / name).write_text(text, encoding="utf-8")
    return base


# ---------------------------------------------------------------------------
# _validate_candidate
# ---------------------------------------------------------------------------


def test_validate_candidate_accepts_valid_tree() -> None:
    assert _validate_candidate(dict(BASE_TREE)) == BASE_TREE


def test_validate_candidate_rejects_non_mapping() -> None:
    with pytest.raises(ProposalError, match="must return a mapping"):
        _validate_candidate(["not", "a", "mapping"])


def test_validate_candidate_rejects_off_surface_names() -> None:
    with pytest.raises(ProposalError, match="off-surface"):
        _validate_candidate({"evil.py": "print('hi')"})


def test_validate_candidate_rejects_non_string_values() -> None:
    with pytest.raises(ProposalError, match="map str filenames to str"):
        _validate_candidate({"systemprompt.md": 42})


def test_validate_candidate_rejects_empty_tree() -> None:
    with pytest.raises(ProposalError, match="empty harness tree"):
        _validate_candidate({"systemprompt.md": "   "})


# ---------------------------------------------------------------------------
# _pass_rate
# ---------------------------------------------------------------------------


def test_pass_rate() -> None:
    assert _result("base", 3, 4).pass_rate == 0.75


def test_pass_rate_empty_run_is_zero() -> None:
    assert _result("base", 0, 0).pass_rate == 0.0


# ---------------------------------------------------------------------------
# run_cycle — adoption
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cycle_adopts_strict_winner(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    candidate_tree = {**BASE_TREE, "systemprompt.md": "You are a better agent."}

    def propose(_task: str, _base: dict[str, str], _lib: str) -> dict[str, str]:
        return candidate_tree

    def evaluator(
        _tasks: Any, _candidate: Path | None, _trials: int
    ) -> tuple[EvalResult, EvalResult]:
        return _result("base", 6, 10), _result("candidate", 9, 10)

    report = run_cycle(
        task="t1",
        domain="coding",
        base_dir=base,
        work_dir=tmp_path / "work",
        tasks=(_task(),),
        propose=propose,
        evaluator=evaluator,
    )

    assert report.adopted is True
    assert report.scores == {"base": 0.6, "candidate": 0.9}
    assert report.selection.winner == "candidate"
    assert report.adopted_dir is not None
    adopted = (report.adopted_dir / "systemprompt.md").read_text(encoding="utf-8")
    assert adopted == "You are a better agent."
    assert report.proposals == 1


@pytest.mark.asyncio
async def test_cycle_persists_lesson_to_library(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    library_root = tmp_path / "library"

    def propose(_t: str, _b: dict[str, str], _l: str) -> dict[str, str]:
        return {**BASE_TREE, "systemprompt.md": "better"}

    def evaluator(
        _tasks: Any, _c: Path | None, _tr: int
    ) -> tuple[EvalResult, EvalResult]:
        return _result("base", 5, 10), _result("candidate", 8, 10)

    run_cycle(
        task="t1",
        domain="coding",
        base_dir=base,
        work_dir=tmp_path / "work",
        tasks=(_task(),),
        propose=propose,
        evaluator=evaluator,
        library_root=library_root,
    )

    experience = library_root / "coding" / "harnesses" / "t1" / "EXPERIENCE.md"
    assert experience.is_file()
    text = experience.read_text(encoding="utf-8")
    assert "t1" in text
    assert "cue" in text
    assert "lesson" in text
    assert "evidence" in text
    assert "candidate 0.800 vs base 0.500" in text
    assert (library_root / "coding" / "INDEX.md").is_file()


# ---------------------------------------------------------------------------
# run_cycle — non-adoption
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cycle_keeps_base_on_tie(tmp_path: Path) -> None:
    base = _make_base(tmp_path)

    def propose(_t: str, _b: dict[str, str], _l: str) -> dict[str, str]:
        return {**BASE_TREE, "systemprompt.md": "different"}

    def evaluator(
        _tasks: Any, _c: Path | None, _tr: int
    ) -> tuple[EvalResult, EvalResult]:
        return _result("base", 5, 10), _result("candidate", 5, 10)

    report = run_cycle(
        task="t1",
        domain="coding",
        base_dir=base,
        work_dir=tmp_path / "work",
        tasks=(_task(),),
        propose=propose,
        evaluator=evaluator,
    )

    assert report.adopted is False
    assert report.adopted_dir is None
    assert "no strict winner" in report.rejection
    # No library entry was written.
    assert not (tmp_path / "work" / "library" / "coding" / "harnesses").exists()


@pytest.mark.asyncio
async def test_cycle_keeps_base_on_regression(tmp_path: Path) -> None:
    base = _make_base(tmp_path)

    def propose(_t: str, _b: dict[str, str], _l: str) -> dict[str, str]:
        return {**BASE_TREE, "systemprompt.md": "worse"}

    def evaluator(
        _tasks: Any, _c: Path | None, _tr: int
    ) -> tuple[EvalResult, EvalResult]:
        return _result("base", 9, 10), _result("candidate", 4, 10)

    report = run_cycle(
        task="t1",
        domain="coding",
        base_dir=base,
        work_dir=tmp_path / "work",
        tasks=(_task(),),
        propose=propose,
        evaluator=evaluator,
    )

    assert report.adopted is False
    assert report.scores["candidate"] < report.scores["base"]


@pytest.mark.asyncio
async def test_cycle_rejects_malformed_proposal_without_probing(tmp_path: Path) -> None:
    """A bad proposal scores the base arm and never probes a candidate."""
    base = _make_base(tmp_path)
    probed: list[str] = []

    def propose(_t: str, _b: dict[str, str], _l: str) -> dict[str, str]:
        return {"evil.py": "nope"}

    def evaluator(
        _tasks: Any, _c: Path | None, _tr: int
    ) -> tuple[EvalResult, EvalResult]:
        probed.append("probed")
        return _result("base", 1, 1), _result("candidate", 1, 1)

    report = run_cycle(
        task="t1",
        domain="coding",
        base_dir=base,
        work_dir=tmp_path / "work",
        tasks=(_task(),),
        propose=propose,
        evaluator=evaluator,
    )

    assert report.adopted is False
    assert report.candidate is None
    assert report.proposals == 0
    assert "off-surface" in report.rejection
    # Only the base arm was scored, once.
    assert probed == ["probed"]


@pytest.mark.asyncio
async def test_cycle_emits_progress_events(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    events: list[str] = []

    def propose(_t: str, _b: dict[str, str], _l: str) -> dict[str, str]:
        return {**BASE_TREE, "systemprompt.md": "x"}

    def evaluator(
        _tasks: Any, _c: Path | None, _tr: int
    ) -> tuple[EvalResult, EvalResult]:
        return _result("base", 1, 2), _result("candidate", 2, 2)

    run_cycle(
        task="t1",
        domain="coding",
        base_dir=base,
        work_dir=tmp_path / "work",
        tasks=(_task(),),
        propose=propose,
        evaluator=evaluator,
        on_event=events.append,
    )

    joined = " | ".join(events)
    assert "proposing" in joined
    assert "probing" in joined
    assert "adopted" in joined


@pytest.mark.asyncio
async def test_cycle_composes_per_file_from_winner(tmp_path: Path) -> None:
    """A candidate that changes one file leaves the other from base."""
    base = _make_base(tmp_path)

    def propose(_t: str, _b: dict[str, str], _l: str) -> dict[str, str]:
        # Change only the system prompt; leave tool guidance identical.
        return {**BASE_TREE, "systemprompt.md": "new prompt"}

    def evaluator(
        _tasks: Any, _c: Path | None, _tr: int
    ) -> tuple[EvalResult, EvalResult]:
        return _result("base", 1, 2), _result("candidate", 2, 2)

    report = run_cycle(
        task="t1",
        domain="coding",
        base_dir=base,
        work_dir=tmp_path / "work",
        tasks=(_task(),),
        propose=propose,
        evaluator=evaluator,
    )

    assert report.adopted is True
    assert (report.adopted_dir / "systemprompt.md").read_text() == "new prompt"
    assert (report.adopted_dir / "tool_guidance.md").read_text() == BASE_TREE[
        "tool_guidance.md"
    ]


# ---------------------------------------------------------------------------
# build_proposer
# ---------------------------------------------------------------------------


def test_build_proposer_parses_json_reply() -> None:
    reply = json.dumps({**BASE_TREE, "systemprompt.md": "from the model"})
    proposer = build_proposer(lambda _prompt: reply)
    tree = proposer("task", dict(BASE_TREE), "")
    assert tree["systemprompt.md"] == "from the model"


def test_build_proposer_rejects_non_json() -> None:
    proposer = build_proposer(lambda _prompt: "not json at all")
    with pytest.raises(ProposalError, match="did not return JSON"):
        proposer("task", dict(BASE_TREE), "")


def test_build_proposer_prompt_includes_inputs() -> None:
    seen: list[str] = []

    def ask(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps(BASE_TREE)

    proposer = build_proposer(ask)
    proposer("my task", dict(BASE_TREE), "LIBRARY INDEX")

    prompt = seen[0]
    assert "my task" in prompt
    assert "LIBRARY INDEX" in prompt
    assert "systemprompt.md" in prompt


def test_build_proposer_rejects_off_surface_reply() -> None:
    proposer = build_proposer(lambda _p: json.dumps({"evil.py": "x"}))
    with pytest.raises(ProposalError, match="off-surface"):
        proposer("task", dict(BASE_TREE), "")


# ---------------------------------------------------------------------------
# default_ask
# ---------------------------------------------------------------------------


def test_default_ask_requires_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_PROPOSER_MODEL", raising=False)
    with pytest.raises(ProposalError, match="HOME_SWE_HOME_PROPOSER_MODEL"):
        default_ask("prompt")


def test_default_ask_calls_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setenv("HOME_SWE_HOME_PROPOSER_MODEL", "some/model")
    monkeypatch.setenv("HOME_SWE_HOME_PROPOSER_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=self)

        def create(self, **kwargs: Any) -> Any:
            captured["create"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="reply"))]
            )

    monkeypatch.setattr("openai.OpenAI", FakeClient)
    assert default_ask("my prompt") == "reply"
    assert captured["create"]["model"] == "some/model"
    assert captured["create"]["messages"] == [{"role": "user", "content": "my prompt"}]
    assert captured["client"]["api_key"] == "or-key"


# ---------------------------------------------------------------------------
# _default_evaluator
# ---------------------------------------------------------------------------


def test_default_evaluator_uses_compare_arms(tmp_path: Path) -> None:
    from home_swe_home import orchestrate

    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    seen: dict[str, Any] = {}

    def fake_compare_arms(tasks, base_runner, candidate_runner, **kwargs):
        seen["tasks"] = tasks
        seen["candidate_dir"] = kwargs.get("candidate_dir")
        # Exercise both runners so their wiring is covered.
        base_runner("p", None)
        candidate_runner("p", None)
        return _result("base", 1, 2), _result("candidate", 2, 2)

    import home_swe_home.eval as eval_mod

    original = eval_mod.compare_arms
    eval_mod.compare_arms = fake_compare_arms  # type: ignore[assignment]
    try:
        evaluator = orchestrate._default_evaluator(candidate_dir, trials=3)
        base, candidate = evaluator((_task(),), candidate_dir, 3)
    finally:
        eval_mod.compare_arms = original  # type: ignore[assignment]

    assert base.passes == 1
    assert candidate.passes == 2
    assert seen["candidate_dir"] == candidate_dir


def test_score_base_without_evaluator(tmp_path: Path) -> None:
    """With no evaluator, the base arm is scored through eval.evaluate."""
    from home_swe_home import orchestrate

    calls: list[str] = []

    def fake_evaluate(tasks, runner, *, trials=1):
        calls.append("evaluate")
        # The caller has cli_runner patched; exercise the runner so the
        # wiring is covered without spawning a subprocess.
        assert runner("prompt", None) == "out"
        return _result("base", 1, 1)

    import home_swe_home.eval as eval_mod

    original = eval_mod.evaluate
    eval_mod.evaluate = fake_evaluate  # type: ignore[assignment]
    try:
        # Patch cli_runner at the source module so _score_base's local
        # ``from .eval import cli_runner`` resolves to the mock.
        with patch("home_swe_home.eval.cli_runner", return_value="out"):
            result = orchestrate._score_base((_task(),), None, 1, lambda _m: None)
    finally:
        eval_mod.evaluate = original  # type: ignore[assignment]

    assert result.passes == 1
    assert calls == ["evaluate"]


def test_score_base_with_evaluator() -> None:
    from home_swe_home import orchestrate

    def evaluator(tasks, candidate, trials):
        return _result("base", 7, 8), _result("candidate", 0, 1)

    result = orchestrate._score_base((_task(),), evaluator, 1, lambda _m: None)
    assert result.passes == 7


@pytest.mark.asyncio
async def test_cycle_uses_default_evaluator_when_none_given(tmp_path: Path) -> None:
    """run_cycle's evaluator=None branch builds and calls _default_evaluator."""

    base = _make_base(tmp_path)
    seen: dict[str, Any] = {}

    def propose(_t: str, _b: dict[str, str], _l: str) -> dict[str, str]:
        return {**BASE_TREE, "systemprompt.md": "better"}

    def fake_compare_arms(tasks, base_runner, candidate_runner, **kwargs):
        seen["candidate_dir"] = kwargs.get("candidate_dir")
        base_runner("p", None)
        candidate_runner("p", None)
        return _result("base", 1, 2), _result("candidate", 2, 2)

    import home_swe_home.eval as eval_mod

    original = eval_mod.compare_arms
    eval_mod.compare_arms = fake_compare_arms  # type: ignore[assignment]
    try:
        report = run_cycle(
            task="t1",
            domain="coding",
            base_dir=base,
            work_dir=tmp_path / "work",
            tasks=(_task(),),
            propose=propose,
            # Deliberately omit evaluator so the fallback branch is taken.
        )
    finally:
        eval_mod.compare_arms = original  # type: ignore[assignment]

    assert report.adopted is True
    assert seen["candidate_dir"] is not None
