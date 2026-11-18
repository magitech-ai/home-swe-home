"""Tests for per-repo verification command discovery."""

from __future__ import annotations

from magecode.utils.verify import DEFAULT_CHECKS, verification_commands


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
