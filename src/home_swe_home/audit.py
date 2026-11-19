"""Build durable, explicitly-shaped audit records for independent reviews.

The record shape is a contract: a review that fails to emit latency or token
data produces no record rather than an incomplete one. Keeping this in Python
makes the shape testable instead of hiding it in workflow shell code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VERDICT_FIELDS = (
    "verdict",
    "summary",
    "findings",
    "elapsed_seconds",
    "prompt_tokens",
    "completion_tokens",
)


def build_audit_record(
    *,
    verdict: dict[str, Any] | None,
    error: str,
    pr: int,
    commit: str,
    trigger_issue: int,
    author_model: str,
    reviewer_model: str,
    reviewer_provider: str,
    workflow_run_id: int,
    recorded_at: str,
) -> dict[str, Any]:
    """Return a complete audit record, failing closed on missing data."""
    record: dict[str, Any] = {
        "status": "ok" if verdict is not None else "error",
        "pr": pr,
        "commit": commit,
        "trigger_issue": trigger_issue,
        "author_model": author_model,
        "reviewer_model": reviewer_model,
        "reviewer_provider": reviewer_provider,
        "workflow_run_id": workflow_run_id,
        "recorded_at": recorded_at,
    }
    if verdict is None:
        record["error"] = error
        return record
    missing = [field for field in VERDICT_FIELDS if field not in verdict]
    if missing:
        raise ValueError(f"review output missing required fields: {', '.join(missing)}")
    record.update({field: verdict[field] for field in VERDICT_FIELDS})
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hsh-audit")
    parser.add_argument("--verdict", required=True, metavar="FILE")
    parser.add_argument("--error-file", required=True, metavar="FILE")
    parser.add_argument("--out", required=True, metavar="FILE")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--trigger-issue", required=True, type=int)
    parser.add_argument("--author-model", required=True)
    parser.add_argument("--reviewer-model", required=True)
    parser.add_argument("--reviewer-provider", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--recorded-at", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        verdict_path = Path(args.verdict)
        verdict = (
            json.loads(verdict_path.read_text()) if verdict_path.is_file() else None
        )
        error = Path(args.error_file).read_text(encoding="utf-8")
        record = build_audit_record(
            verdict=verdict,
            error=error,
            pr=args.pr,
            commit=args.commit,
            trigger_issue=args.trigger_issue,
            author_model=args.author_model,
            reviewer_model=args.reviewer_model,
            reviewer_provider=args.reviewer_provider,
            workflow_run_id=args.run_id,
            recorded_at=args.recorded_at,
        )
    except Exception as error:
        print(f"hsh-audit: {error}", file=sys.stderr)
        return 2
    Path(args.out).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
