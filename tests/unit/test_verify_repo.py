"""Tests for the verify_repo tool."""

from __future__ import annotations

from anima import Context

from home_swe_home.tools.verify_repo import VerifyRepoService


def test_verify_repo_runs_default_checks(monkeypatch, tmp_path):
    calls: list[tuple[str, object]] = []

    def fake(command, cwd):
        calls.append((command, cwd))
        return (0, "")

    monkeypatch.setattr("home_swe_home.tools.verify_repo.default_runner", fake)
    ctx = Context()
    ctx.use(VerifyRepoService)
    out = ctx.verify_repo(path=str(tmp_path))
    assert "4/4 checks passed" in out
    assert len(calls) == 4
