"""Tests for the durable audit record contract."""

from __future__ import annotations

import json

import pytest

from home_swe_home import audit

CONTEXT = {
    "pr": 50,
    "commit": "abc123",
    "trigger_issue": 49,
    "author_model": "gemini-4-hydrogen",
    "reviewer_model": "google/gemma-4-31b-it",
    "reviewer_provider": "nvidia",
    "workflow_run_id": 44603167634,
    "recorded_at": "2026-11-19T19:56:16Z",
}
VERDICT = {
    "verdict": "APPROVE",
    "summary": "ok",
    "findings": [],
    "elapsed_seconds": 12.3,
    "prompt_tokens": 100,
    "completion_tokens": 20,
}


def test_record_carries_every_required_field() -> None:
    record = audit.build_audit_record(verdict=VERDICT, error="", **CONTEXT)
    assert record["status"] == "ok"
    for field in audit.VERDICT_FIELDS:
        assert record[field] == VERDICT[field]
    for field, value in CONTEXT.items():
        assert record[field] == value


def test_evidence_check_is_recorded_when_present() -> None:
    checks = [{"evidence": "src/a.py:1", "status": "diff"}]
    record = audit.build_audit_record(
        verdict=VERDICT, error="", evidence_check=checks, **CONTEXT
    )
    assert record["evidence_check"] == checks


def test_trial_fields_are_recorded_when_present() -> None:
    verdict = dict(VERDICT)
    verdict["trials"] = 3
    verdict["approvals"] = 2
    verdict["trial_records"] = [{"verdict": "APPROVE"}]
    record = audit.build_audit_record(verdict=verdict, error="", **CONTEXT)
    assert record["trials"] == 3
    assert record["approvals"] == 2
    assert record["trial_records"] == verdict["trial_records"]


def test_missing_cost_fields_fail_closed() -> None:
    bad = dict(VERDICT)
    del bad["prompt_tokens"]
    with pytest.raises(ValueError, match="prompt_tokens"):
        audit.build_audit_record(verdict=bad, error="", **CONTEXT)


def test_error_record_has_message_and_no_verdict_fields() -> None:
    record = audit.build_audit_record(
        verdict=None, error="Request timed out.", **CONTEXT
    )
    assert record["status"] == "error"
    assert record["error"] == "Request timed out."
    assert "verdict" not in record


def test_main_writes_record(monkeypatch, tmp_path) -> None:
    verdict = tmp_path / "verdict.json"
    verdict.write_text(json.dumps(VERDICT), encoding="utf-8")
    err = tmp_path / "error.txt"
    err.write_text("", encoding="utf-8")
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps([{"evidence": "src/a.py:1", "status": "diff"}]), encoding="utf-8"
    )
    out = tmp_path / "record.json"
    code = audit.main(
        [
            "--verdict",
            str(verdict),
            "--error-file",
            str(err),
            "--out",
            str(out),
            "--pr",
            "50",
            "--commit",
            "abc123",
            "--trigger-issue",
            "49",
            "--author-model",
            "gemini-4-hydrogen",
            "--reviewer-model",
            "google/gemma-4-31b-it",
            "--reviewer-provider",
            "nvidia",
            "--run-id",
            "44603167634",
            "--recorded-at",
            "2026-11-19T19:56:16Z",
            "--evidence-check",
            str(checks),
        ]
    )
    assert code == 0
    payload = json.loads(out.read_text())
    assert payload["status"] == "ok"
    assert payload["evidence_check"][0]["status"] == "diff"


def test_main_fails_closed_on_bad_verdict(tmp_path, capsys) -> None:
    verdict = tmp_path / "verdict.json"
    verdict.write_text(json.dumps({"verdict": "APPROVE"}), encoding="utf-8")
    err = tmp_path / "error.txt"
    err.write_text("", encoding="utf-8")
    code = audit.main(
        [
            "--verdict",
            str(verdict),
            "--error-file",
            str(err),
            "--out",
            str(tmp_path / "record.json"),
            "--pr",
            "50",
            "--commit",
            "abc123",
            "--trigger-issue",
            "49",
            "--author-model",
            "a",
            "--reviewer-model",
            "b",
            "--reviewer-provider",
            "nvidia",
            "--run-id",
            "1",
            "--recorded-at",
            "2026-11-19T00:00:00Z",
        ]
    )
    assert code == 2
    assert "missing required fields" in capsys.readouterr().err
