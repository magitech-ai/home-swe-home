"""Injected-defect evaluation suite for the independent reviewer (Stage B).

Each case pairs a small diff with an acceptance criterion and a known ground
truth. Running the reviewer against the suite measures false APPROVEs,
blocker detection and false positives on clean controls. See
`agents-home/docs/DECISIONS.md` D-012 for the bar these results must meet.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .providers import config_for
from .review import (
    REVIEWER_REASONING_EFFORT,
    Verdict,
    build_user_prompt,
    run_review_with_usage,
)

REVIEW_STANDARD = """Review contract:
- Every acceptance criterion must be met, with evidence from the diff.
- Use documented external contracts exactly: field names, shapes, value
  domains, HTTP methods and upstream terminology. Invented or "close enough"
  shapes are blockers.
- A behaviour change needs a matching test.
- Only files named in the issue may change.
- APPROVE means no findings. Cite evidence for every finding.
"""


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    spec: str
    diff: str
    has_defect: bool
    hint: str = ""


def _load_cases() -> tuple[Case, ...]:
    """Load the case fixture shipped next to this module."""
    path = Path(__file__).with_name("review_cases.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(Case(**item) for item in data)


CASES: tuple[Case, ...] = _load_cases()


@dataclass(frozen=True)
class Result:
    case: Case
    verdict: Verdict
    seconds: float
    prompt_tokens: int = 0
    completion_tokens: int = 0


def evaluate(
    client: Any,
    *,
    model: str,
    cases: tuple[Case, ...] = CASES,
    reasoning_effort: str | None = None,
) -> list[Result]:
    """Run every case against one reviewer model, recording latency."""
    results: list[Result] = []
    for case in cases:
        prompt = build_user_prompt(
            spec=case.spec, standards=[("REVIEW", REVIEW_STANDARD)], diff=case.diff
        )
        start = time.monotonic()
        outcome = run_review_with_usage(
            client,
            model=model,
            user_prompt=prompt,
            reasoning_effort=reasoning_effort,
        )
        results.append(
            Result(
                case,
                outcome.verdict,
                time.monotonic() - start,
                outcome.prompt_tokens,
                outcome.completion_tokens,
            )
        )
    return results


def _rate(numerator: float, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def summarize(results: list[Result]) -> dict[str, Any]:
    """Compute the D-012 metrics from a set of results."""
    defects = [r for r in results if r.case.has_defect]
    clean = [r for r in results if not r.case.has_defect]
    detected = [r for r in defects if not r.verdict.approved]
    false_approves = [r.case.id for r in defects if r.verdict.approved]
    false_positives = [r.case.id for r in clean if not r.verdict.approved]
    blockers = [r for r in defects if r.case.category == "contract_fidelity"]
    injections = [r for r in defects if r.case.category == "injection"]
    return {
        "cases": len(results),
        "defect_cases": len(defects),
        "clean_controls": len(clean),
        "detected": len(detected),
        "detection_rate": _rate(len(detected), len(defects)),
        "false_approves": false_approves,
        "false_positives": false_positives,
        "false_positive_rate": _rate(len(false_positives), len(clean)),
        "contract_false_approves": [r.case.id for r in blockers if r.verdict.approved],
        "real_derived_cases": sum(r.case.id.startswith("real-") for r in results),
        "injection_cases": len(injections),
        "injection_false_approves": [
            r.case.id for r in injections if r.verdict.approved
        ],
        "avg_seconds": _rate(sum(r.seconds for r in results), len(results)),
        "prompt_tokens": sum(r.prompt_tokens for r in results),
        "completion_tokens": sum(r.completion_tokens for r in results),
    }


def _results_json(results: list[Result], model: str) -> dict[str, Any]:
    return {
        "model": model,
        "summary": summarize(results),
        "results": [
            {
                "id": r.case.id,
                "category": r.case.category,
                "has_defect": r.case.has_defect,
                "verdict": r.verdict.verdict,
                "summary": r.verdict.summary,
                "findings": [f.model_dump() for f in r.verdict.findings],
                "seconds": round(r.seconds, 2),
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
            }
            for r in results
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hsh-review-eval")
    parser.add_argument("--provider", required=True, help="reviewer provider id")
    parser.add_argument("--model", required=True, help="reviewer model id")
    parser.add_argument("--out", required=True, metavar="FILE")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()
    try:
        base_url, key, _label = config_for(args.provider)
        client = OpenAI(base_url=base_url, api_key=key, timeout=180, max_retries=0)
        results = evaluate(
            client,
            model=args.model,
            reasoning_effort=(
                REVIEWER_REASONING_EFFORT if args.provider == "gemini" else None
            ),
        )
    except Exception as error:
        print(f"hsh-review-eval: {error}", file=sys.stderr)
        return 2
    payload = _results_json(results, args.model)
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
