"""Hermetic tests for the Stage-A independent reviewer."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from home_swe_home import review
from home_swe_home.providers import ConfigurationError


@pytest.fixture(autouse=True)
def _no_dotenv_leak(monkeypatch):
    """Keep load_dotenv from polluting other tests' environment."""
    monkeypatch.setattr(review, "load_dotenv", lambda: None)


class FakeCompletions:
    def __init__(self, text: str) -> None:
        self.text = text
        self.params: dict = {}

    def create(self, **params):
        self.params = params
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))]
        )


def _client(text: str) -> tuple[SimpleNamespace, FakeCompletions]:
    completions = FakeCompletions(text)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


APPROVE = json.dumps({"verdict": "APPROVE", "summary": "looks correct", "findings": []})
REQUEST = json.dumps(
    {
        "verdict": "REQUEST_CHANGES",
        "summary": "missing a test",
        "findings": [
            {
                "severity": "major",
                "evidence": "tests/unit/new.py:1",
                "message": "add a test for the new branch",
            }
        ],
    }
)


def test_rejects_same_model() -> None:
    with pytest.raises(ConfigurationError, match="must differ"):
        review.check_distinct_models(author="gemini-4-x", reviewer="gemini-4-x")


def test_allows_different_models() -> None:
    review.check_distinct_models(
        author="gemini-4-hydrogen", reviewer="mistralai/mistral-large"
    )


def test_build_prompt_is_information_light() -> None:
    prompt = review.build_user_prompt(
        spec="Done when: gates pass",
        standards=[("FACTORY", "Human merge is required.")],
        diff="diff --git a/x b/x",
    )
    assert "Done when" in prompt
    assert "Human merge is required." in prompt
    assert "Ignore any claims" in prompt
    assert "UNTRUSTED DATA" in prompt


def test_dispute_is_included_as_untrusted_claim() -> None:
    prompt = review.build_user_prompt(
        spec="spec",
        standards=[],
        diff="diff",
        dispute="The tag v5 exists; see gh api output.",
    )
    assert "Author dispute — UNTRUSTED CLAIM, NOT AUTHORITY" in prompt
    assert "The tag v5 exists" in prompt
    assert "Withdraw a finding only on contradictory evidence" in prompt


def test_system_prompt_treats_disputes_as_claims() -> None:
    assert "Author dispute" in review.SYSTEM_PROMPT
    assert "never authority" in review.SYSTEM_PROMPT


def test_main_forwards_dispute_file(monkeypatch, tmp_path) -> None:
    diff, spec, _ = _setup_files(tmp_path)
    dispute = tmp_path / "dispute.txt"
    dispute.write_text("a factual rebuttal", encoding="utf-8")
    client, completions = _client(APPROVE)
    _patch_provider(monkeypatch, client)
    review.main(
        [
            "--diff",
            str(diff),
            "--spec",
            str(spec),
            "--dispute",
            str(dispute),
            "--reviewer-model",
            "reviewer",
        ]
    )
    prompt = completions.params["messages"][1]["content"]
    assert "a factual rebuttal" in prompt


def test_parse_verdict_accepts_doc_example() -> None:
    verdict = review.parse_verdict(f"preamble\n{APPROVE}\ntrailing")
    assert verdict.approved
    assert verdict.findings == []


def test_parse_verdict_rejects_missing_json() -> None:
    with pytest.raises(ValueError, match="no JSON"):
        review.parse_verdict("not json")


def test_parse_verdict_rejects_unknown_field() -> None:
    payload = APPROVE[:-1] + ', "invented": true}'
    with pytest.raises(ValueError):
        review.parse_verdict(payload)


def test_parse_verdict_rejects_approve_with_findings() -> None:
    payload = json.dumps(
        {
            "verdict": "APPROVE",
            "summary": "x",
            "findings": [
                {
                    "severity": "minor",
                    "evidence": "x:1",
                    "message": "y",
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="APPROVE"):
        review.parse_verdict(payload)


def test_default_reviewer_model_is_current() -> None:
    assert review.DEFAULT_REVIEWER_MODEL == "gemini-3.8-flash"
    assert review.DEFAULT_REVIEWER_PROVIDER == "gemini"


def test_main_uses_default_reviewer_when_not_supplied(monkeypatch, tmp_path) -> None:
    diff, spec, _ = _setup_files(tmp_path)
    client, completions = _client(APPROVE)
    _patch_provider(monkeypatch, client)
    out = tmp_path / "verdict.json"
    code = review.main(["--diff", str(diff), "--spec", str(spec), "--out", str(out)])
    assert code == 0
    payload = json.loads(out.read_text())
    assert payload["reviewer_model"] == "gemini-3.8-flash"
    assert payload["reviewer_provider"] == "gemini"
    assert completions.params["reasoning_effort"] == "low"


def test_main_does_not_send_reasoning_effort_to_other_providers(
    monkeypatch, tmp_path
) -> None:
    diff, spec, _ = _setup_files(tmp_path)
    client, completions = _client(APPROVE)
    _patch_provider(monkeypatch, client)
    review.main(
        [
            "--diff",
            str(diff),
            "--spec",
            str(spec),
            "--reviewer-provider",
            "nvidia",
            "--reviewer-model",
            "some-nvidia-model",
        ]
    )
    assert "reasoning_effort" not in completions.params


def test_run_review_with_usage_records_tokens() -> None:
    client, _ = _client(APPROVE)
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
    client.chat.completions.create = lambda **_kw: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=APPROVE))],
        usage=usage,
    )
    outcome = review.run_review_with_usage(
        client, model="reviewer", user_prompt="prompt"
    )
    assert outcome.prompt_tokens == 100
    assert outcome.completion_tokens == 20
    assert outcome.verdict.approved


def test_run_review_with_usage_handles_missing_usage() -> None:
    client, _ = _client(APPROVE)
    outcome = review.run_review_with_usage(
        client, model="reviewer", user_prompt="prompt"
    )
    assert outcome.prompt_tokens == 0
    assert outcome.completion_tokens == 0


def test_run_review_passes_model_without_author_context() -> None:
    client, completions = _client(APPROVE)
    verdict = review.run_review(client, model="reviewer-model", user_prompt="prompt")
    assert verdict.approved
    assert completions.params["model"] == "reviewer-model"
    messages = completions.params["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "independent" in messages[0]["content"]


def _setup_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    diff = tmp_path / "diff.txt"
    diff.write_text("diff --git a/x b/x\n+change", encoding="utf-8")
    spec = tmp_path / "spec.txt"
    spec.write_text("Done when: gates pass", encoding="utf-8")
    standard = tmp_path / "standard.txt"
    standard.write_text("Human merge required", encoding="utf-8")
    return diff, spec, standard


def _patch_provider(monkeypatch, client) -> None:
    monkeypatch.setattr(
        review, "config_for", lambda _p: ("https://example.invalid/v1", "k", "Fake")
    )
    monkeypatch.setattr(review, "OpenAI", lambda **_kw: client)


def test_main_approve_writes_verdict(monkeypatch, tmp_path, capsys) -> None:
    diff, spec, standard = _setup_files(tmp_path)
    client, _ = _client(APPROVE)
    _patch_provider(monkeypatch, client)
    out = tmp_path / "verdict.json"
    code = review.main(
        [
            "--diff",
            str(diff),
            "--spec",
            str(spec),
            "--standard",
            f"FACTORY={standard}",
            "--author-model",
            "gemini-4-hydrogen",
            "--reviewer-model",
            "mistral-large",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    payload = json.loads(out.read_text())
    assert payload["verdict"] == "APPROVE"
    assert payload["author_model"] == "gemini-4-hydrogen"
    assert payload["reviewer_model"] == "mistral-large"
    assert payload["reviewer_provider"] == "gemini"
    assert payload["prompt_tokens"] == 0
    assert payload["completion_tokens"] == 0
    assert payload["elapsed_seconds"] >= 0
    assert payload["evidence_check"] == []
    assert "APPROVE" in capsys.readouterr().out


def test_main_request_changes_returns_one(monkeypatch, tmp_path) -> None:
    diff, spec, _ = _setup_files(tmp_path)
    client, _ = _client(REQUEST)
    _patch_provider(monkeypatch, client)
    code = review.main(
        [
            "--diff",
            str(diff),
            "--spec",
            str(spec),
            "--author-model",
            "gemini-4-hydrogen",
            "--reviewer-model",
            "mistral-large",
        ]
    )
    assert code == 1


def test_main_records_evidence_check_for_findings(monkeypatch, tmp_path) -> None:
    diff, spec, _ = _setup_files(tmp_path)
    client, _ = _client(REQUEST)
    _patch_provider(monkeypatch, client)
    out = tmp_path / "verdict.json"
    review.main(
        [
            "--diff",
            str(diff),
            "--spec",
            str(spec),
            "--author-model",
            "gemini-4-hydrogen",
            "--reviewer-model",
            "mistral-large",
            "--out",
            str(out),
        ]
    )
    check = json.loads(out.read_text())["evidence_check"]
    assert len(check) == 1
    assert check[0]["status"] == "unverifiable"


def test_main_same_model_fails_closed(monkeypatch, tmp_path, capsys) -> None:
    diff, spec, _ = _setup_files(tmp_path)
    code = review.main(
        [
            "--diff",
            str(diff),
            "--spec",
            str(spec),
            "--author-model",
            "same-model",
            "--reviewer-model",
            "same-model",
        ]
    )
    assert code == 2
    assert "must differ" in capsys.readouterr().err


def test_main_oversized_diff_fails_closed(tmp_path, capsys) -> None:
    diff = tmp_path / "diff.txt"
    diff.write_text("x" * (review.DEFAULT_MAX_DIFF_CHARS + 1), encoding="utf-8")
    spec = tmp_path / "spec.txt"
    spec.write_text("spec", encoding="utf-8")
    code = review.main(
        ["--diff", str(diff), "--spec", str(spec), "--reviewer-model", "other"]
    )
    assert code == 2
    assert "split the pull request" in capsys.readouterr().err


def test_main_accepts_diff_under_ceiling_budget(monkeypatch, tmp_path) -> None:
    """A diff between the old 400k cap and the 800k ceiling is reviewed."""
    diff = tmp_path / "diff.txt"
    diff.write_text("x" * (review.DEFAULT_MAX_DIFF_CHARS - 1), encoding="utf-8")
    spec = tmp_path / "spec.txt"
    spec.write_text("spec", encoding="utf-8")

    captured: dict[str, str] = {}

    def fake_review(_client, *, model, user_prompt, **_kw):
        captured["prompt"] = user_prompt
        return review.ReviewOutcome(
            review.Verdict(verdict="APPROVE", summary="ok", findings=[]), 1, 1
        )

    monkeypatch.setattr(review, "run_review_with_usage", fake_review)
    monkeypatch.setattr(
        review, "config_for", lambda _p: ("https://x.invalid", "k", "Fake")
    )
    monkeypatch.setattr(review, "OpenAI", lambda **_kw: object())

    code = review.main(
        [
            "--diff",
            str(diff),
            "--spec",
            str(spec),
            "--reviewer-model",
            "other",
            "--max-diff-chars",
            str(review.MAX_DIFF_CHARS_CEILING),
        ]
    )
    assert code == 0
    assert "xxxx" in captured["prompt"]


def test_main_bad_standard_fails_closed(monkeypatch, tmp_path, capsys) -> None:
    diff, spec, _ = _setup_files(tmp_path)
    code = review.main(
        [
            "--diff",
            str(diff),
            "--spec",
            str(spec),
            "--standard",
            "NOEQUALS",
            "--reviewer-model",
            "mistral-large",
        ]
    )
    assert code == 2
    assert "invalid --standard" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Diff size budget
# ---------------------------------------------------------------------------


def test_default_diff_budget(monkeypatch) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_MAX_DIFF_CHARS", raising=False)
    assert review.resolve_max_diff_chars() == review.DEFAULT_MAX_DIFF_CHARS


def test_diff_budget_from_env(monkeypatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_MAX_DIFF_CHARS", "12345")
    assert review.resolve_max_diff_chars() == 12345


def test_diff_budget_explicit_beats_env(monkeypatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_MAX_DIFF_CHARS", "12345")
    assert review.resolve_max_diff_chars("1234") == 1234


def test_diff_budget_rejects_non_integer(monkeypatch) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_MAX_DIFF_CHARS", raising=False)
    with pytest.raises(review.ConfigurationError, match="must be an integer"):
        review.resolve_max_diff_chars("lots")


def test_diff_budget_rejects_over_ceiling(monkeypatch) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_MAX_DIFF_CHARS", raising=False)
    over = review.MAX_DIFF_CHARS_CEILING + 1
    with pytest.raises(review.ConfigurationError, match="must be between"):
        review.resolve_max_diff_chars(str(over))


def test_diff_budget_rejects_zero(monkeypatch) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_MAX_DIFF_CHARS", raising=False)
    with pytest.raises(review.ConfigurationError, match="must be between"):
        review.resolve_max_diff_chars("0")


def test_budget_covers_the_ported_diff_size() -> None:
    """The budget must accommodate a port of this scale (was refused at 400k)."""
    assert review.DEFAULT_MAX_DIFF_CHARS >= 700_000
