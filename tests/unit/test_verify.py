"""Tests for per-repo verification command discovery."""

from __future__ import annotations

from home_swe_home.utils.verify import DEFAULT_CHECKS, verification_commands


def test_default_when_no_config(tmp_path):
    assert verification_commands(tmp_path) == DEFAULT_CHECKS


def test_commands_from_fenced_block(tmp_path):
    d = tmp_path / "docs" / "agents"
    d.mkdir(parents=True)
    (d / "checks.md").write_text(
        "# Checks\n\n```sh\n# comment\nuv run ruff check .\nuv run pytest\n```\n"
    )
    assert verification_commands(tmp_path) == (
        "uv run ruff check .",
        "uv run pytest",
    )


def test_bash_fence_and_early_stop(tmp_path):
    d = tmp_path / "docs" / "agents"
    d.mkdir(parents=True)
    (d / "checks.md").write_text("```bash\nuv run pytest\n```\nignored\n")
    assert verification_commands(tmp_path) == ("uv run pytest",)


def test_unclosed_block_still_returns_commands(tmp_path):
    d = tmp_path / "docs" / "agents"
    d.mkdir(parents=True)
    (d / "checks.md").write_text("```sh\nuv run pytest\n")
    assert verification_commands(tmp_path) == ("uv run pytest",)


def test_empty_block_falls_back(tmp_path):
    d = tmp_path / "docs" / "agents"
    d.mkdir(parents=True)
    (d / "checks.md").write_text("```sh\n# only a comment\n```\n")
    assert verification_commands(tmp_path) == DEFAULT_CHECKS


def test_run_checks_uses_injected_runner(tmp_path):
    from home_swe_home.utils.verify import CheckResult, run_checks

    seen = []

    def fake(command, cwd):
        seen.append((command, cwd))
        return (0, "") if command == "ok" else (1, "bad")

    results = run_checks(("ok", "bad"), fake, cwd=tmp_path)
    assert results == [
        CheckResult("ok", True, ""),
        CheckResult("bad", False, "bad"),
    ]
    assert all(cwd == tmp_path for _, cwd in seen)


def test_format_results_empty():
    from home_swe_home.utils.verify import format_results

    assert format_results([]) == "No checks to run."


def test_format_results_success():
    from home_swe_home.utils.verify import CheckResult, format_results

    out = format_results([CheckResult("a", True, "noise")])
    assert "[PASS] a" in out and "1/1 checks passed" in out and "noise" not in out


def test_format_results_failure_with_output():
    from home_swe_home.utils.verify import CheckResult, format_results

    out = format_results([CheckResult("a", False, "boom")])
    assert "[FAIL] a" in out and "boom" in out and "0/1 checks passed" in out


def test_default_runner_invokes_subprocess(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from home_swe_home.utils.verify import default_runner

    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("home_swe_home.utils.verify.subprocess.run", fake_run)
    assert default_runner("uv run pytest --cov=src", tmp_path) == (0, "ok")
    assert seen["cwd"] == tmp_path
    assert seen["timeout"] == 600
