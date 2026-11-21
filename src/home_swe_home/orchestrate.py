"""The Propose–Probe–Compose improvement loop.

This module is the orchestrator DESIGN.md calls "external": it drives the
measured harness-improvement cycle end to end. It is deliberately a library
with injected seams rather than an anima Service, because the loop is a
run-to-completion job, not a capability mounted on a Context.

The cycle is:

1. **Propose** — ask a model to rewrite the editable harness given the current
   tree, the domain's library entries, and the acceptance criteria. The
   proposer returns a candidate harness tree (data, not code).
2. **Probe** — score the candidate and the base arm on the same fixed task
   suite via ``eval.compare_arms``, which interleaves the arms so time drift
   and provider rate limits affect both equally.
3. **Compose** — adopt only on a strict, reproducible pass-rate win; compose
   per-file from the best candidate that changed each file, and persist the
   adopted tree plus its cue/lesson/evidence into the domain ``Library``.

Nothing is adopted on a tie or a regression: the base harness is kept. A
candidate that cannot be validated as a harness tree is rejected before any
probe runs, so a malformed proposal costs no inference.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .eval import EvalResult, Task
from .library import Experience, Library
from .utils.harness import read_tree, validate_tree, write_tree
from .utils.selection import Selection, compose, select

Proposer = Callable[[str, dict[str, str], str], dict[str, str]]
"""Given (task, base_tree, library_index), return a candidate harness tree."""

Evaluator = Callable[[Sequence[Task], Path | None, int], tuple[EvalResult, EvalResult]]
"""Score base vs candidate on the same suite: ``(tasks, candidate_dir, trials)``.

Defaults to :func:`eval.compare_arms`, which interleaves the two arms so time
drift and provider rate limits affect both equally.
"""


class ProposalError(Exception):
    """Raised when a proposal cannot be turned into a usable candidate."""


@dataclass(frozen=True)
class CycleReport:
    """The observable outcome of one improvement cycle."""

    task: str
    domain: str
    scores: dict[str, float]
    selection: Selection
    adopted: bool
    adopted_dir: Path | None
    base: EvalResult
    candidate: EvalResult | None
    rejection: str = ""
    proposals: int = 0


def _default_evaluator(
    candidate_dir: Path | None,
    trials: int,
) -> Evaluator:
    """Build an evaluator that interleaves both arms via eval.compare_arms."""
    from .eval import cli_runner, compare_arms

    def evaluate(
        tasks: Sequence[Task],
        _candidate: Path | None,
        _trials: int,
    ) -> tuple[EvalResult, EvalResult]:
        def base_runner(prompt: str, harness_dir: Path | None) -> str:
            return cli_runner(prompt, harness_dir)

        def candidate_runner(prompt: str, harness_dir: Path | None) -> str:
            return cli_runner(prompt, harness_dir or candidate_dir)

        return compare_arms(
            tuple(tasks),
            base_runner,
            candidate_runner,
            candidate_dir=candidate_dir,
            trials=trials,
        )

    return evaluate


def _validate_candidate(candidate: Any) -> dict[str, str]:
    """Coerce a proposer's return value into a validated harness tree."""
    if not isinstance(candidate, dict):
        raise ProposalError(
            "proposer must return a mapping of filename to text, "
            f"got {type(candidate).__name__}"
        )
    tree: dict[str, str] = {}
    for name, text in candidate.items():
        if not isinstance(name, str) or not isinstance(text, str):
            raise ProposalError("harness tree must map str filenames to str contents")
        tree[name] = text
    error = validate_tree(tree)
    if error:
        raise ProposalError(error)
    return tree


def run_cycle(
    *,
    task: str,
    domain: str,
    base_dir: Path,
    work_dir: Path,
    tasks: Sequence[Task],
    propose: Proposer,
    evaluator: Evaluator | None = None,
    library_root: Path | None = None,
    trials: int = 1,
    on_event: Callable[[str], None] = lambda _message: None,
) -> CycleReport:
    """Run one Propose–Probe–Compose cycle and return its report.

    The candidate is adopted only when its pass rate strictly exceeds the base
    arm's. Ties and regressions keep the base harness and are reported with a
    reason, never silently dropped.
    """
    base = read_tree(base_dir)
    library = Library(library_root or work_dir / "library", domain)
    library_index = library.as_prompt()

    on_event(f"proposing for domain {domain!r}")
    try:
        candidate = _validate_candidate(propose(task, dict(base), library_index))
    except ProposalError as error:
        on_event(f"proposal rejected: {error}")
        base_result = _score_base(tasks, evaluator, trials, on_event)
        return CycleReport(
            task=task,
            domain=domain,
            scores={},
            selection=select({}),
            adopted=False,
            adopted_dir=None,
            base=base_result,
            candidate=None,
            rejection=str(error),
            proposals=0,
        )

    candidate_dir = write_tree(candidate, work_dir / "candidates" / "proposal")
    on_event("probing candidate against base")
    score = evaluator or _default_evaluator(candidate_dir, trials)
    base_result, candidate_result = score(tasks, candidate_dir, trials)

    scores = {
        "base": base_result.pass_rate,
        "candidate": candidate_result.pass_rate,
    }
    selection = select(
        {"base": scores["base"], "candidate": scores["candidate"]}, base="base"
    )

    if selection.winner != "candidate":
        reason = selection.reason
        on_event(f"not adopted: {reason}")
        return CycleReport(
            task=task,
            domain=domain,
            scores=scores,
            selection=selection,
            adopted=False,
            adopted_dir=None,
            base=base_result,
            candidate=candidate_result,
            rejection=reason,
            proposals=1,
        )

    composed = compose(
        base, {"candidate": candidate}, {"candidate": scores["candidate"]}
    )
    adopted_dir = write_tree(composed, work_dir / "adopted")
    experience = Experience(
        task_id=task,
        cue=f"Tasks like {task!r} in the {domain} domain.",
        lesson=selection.reason,
        evidence=(
            f"candidate {scores['candidate']:.3f} vs base "
            f"{scores['base']:.3f} on {len(tasks)} tasks x {trials} trials"
        ),
        confidence="measured",
    )
    library.add(composed, experience, selection)
    on_event(f"adopted: {selection.reason}")
    return CycleReport(
        task=task,
        domain=domain,
        scores=scores,
        selection=selection,
        adopted=True,
        adopted_dir=adopted_dir,
        base=base_result,
        candidate=candidate_result,
        proposals=1,
    )


def _score_base(
    tasks: Sequence[Task],
    evaluator: Evaluator | None,
    trials: int,
    on_event: Callable[[str], None],
) -> EvalResult:
    """Score the base arm alone, used when no candidate reached the probe."""
    on_event("scoring base arm")
    if evaluator is None:
        from .eval import cli_runner, evaluate

        def runner(prompt: str, harness_dir: Path | None) -> str:
            return cli_runner(prompt, harness_dir)

        return evaluate(tuple(tasks), runner, trials=trials)
    base_result, _candidate = evaluator(tasks, None, trials)
    return base_result


def build_proposer(
    ask: Callable[[str], str],
) -> Proposer:
    """Build a proposer from a single-shot ``ask(prompt) -> text`` callable.

    The prompt carries the current harness tree, the domain library index, and
    the task. The reply is parsed as JSON; a malformed reply raises
    :class:`ProposalError` so the caller can score the base arm and report the
    rejection rather than crashing the cycle.
    """

    def propose(
        task: str, base_tree: dict[str, str], library_index: str
    ) -> dict[str, str]:
        prompt = _proposal_prompt(task, base_tree, library_index)
        raw = ask(prompt)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ProposalError(f"proposer did not return JSON: {error}") from error
        return _validate_candidate(parsed)

    return propose


def _proposal_prompt(task: str, base_tree: dict[str, str], library_index: str) -> str:
    """Render the proposer prompt."""
    tree_text = "\n".join(
        f"### {name}\n```\n{content}\n```"
        for name, content in sorted(base_tree.items())
    )
    return (
        "You are improving a coding agent's editable harness (its system prompt "
        "and per-tool guidance). Return ONLY a JSON object mapping filename to "
        "the new file contents. Allowed filenames: "
        f"{', '.join(sorted(_EDITABLE))}.\n\n"
        f"## Task to improve\n{task}\n\n"
        f"## Domain library (prior lessons)\n{library_index or '(empty)'}\n\n"
        f"## Current harness\n{tree_text}\n"
    )


_EDITABLE = ("systemprompt.md", "tool_guidance.md")


def default_ask(prompt: str) -> str:
    """Ask the configured reviewer provider for a completion.

    Reuses the review provider configuration so the improvement loop needs no
    separate credentials. The call is intentionally single-shot with no tools:
    the proposer returns data, not actions.
    """
    from openai import OpenAI

    from .providers import config_for

    provider = os.environ.get("HOME_SWE_HOME_PROPOSER_PROVIDER", "openrouter")
    model = os.environ.get("HOME_SWE_HOME_PROPOSER_MODEL", "")
    if not model:
        raise ProposalError(
            "HOME_SWE_HOME_PROPOSER_MODEL is not set; name the proposer model"
        )
    base_url, key, _label = config_for(provider)
    client = OpenAI(base_url=base_url, api_key=key, timeout=180.0, max_retries=0)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return str(response.choices[0].message.content or "")


__all__ = [
    "CycleReport",
    "ProposalError",
    "build_proposer",
    "default_ask",
    "run_cycle",
]
