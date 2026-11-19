# Review audit

One JSON file per independent review, written by the `Agent review` workflow in
`.github/workflows/agent-review.yml`. Files are append-only; never edit or delete
a record to change a past verdict.

## Record shape

```json
{
  "pr": 48,
  "commit": "<head sha>",
  "trigger_issue": 47,
  "author_model": "gemini-4-hydrogen",
  "reviewer_model": "google/gemma-4-31b-it",
  "reviewer_provider": "nvidia",
  "verdict": "APPROVE",
  "summary": "...",
  "findings": [],
  "elapsed_seconds": 12.3,
  "prompt_tokens": 664,
  "completion_tokens": 42,
  "workflow_run_id": 44528764744,
  "recorded_at": "2026-11-19T13:00:00Z"
}
```

`status` is `error` when the reviewer could not produce a verdict; in that case
`error` carries the failure message and token fields are absent.

This branch is machine-written. Review records are evidence, not source code.
