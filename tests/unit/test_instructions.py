"""Tests for magecode.instructions (InstructionsService)."""

from __future__ import annotations

import pytest
from anima import Context

from magecode.instructions import InstructionsService


@pytest.fixture(autouse=True)
def _no_home(monkeypatch):
    """Keep these tests hermetic: no real agents-home checkout."""
    monkeypatch.setattr("magecode.instructions.find_home", lambda: None)


def _service() -> InstructionsService:
    ctx = Context()
    ctx.use(InstructionsService)
    return ctx.instructions  # type: ignore[return-value]


def test_build_system_instructions_contains_rules():
    content = _service().build(model="test/model")
    assert "magecode" in content
    assert "Rules:" in content
    assert "Use tools" in content


def test_build_system_instructions_contains_system_line():
    content = _service().build(model="test/model")
    assert "System:" in content
    assert "folder:" in content
    assert "date:" in content
    assert "model: test/model" in content


def test_build_system_instructions_no_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = _service().build(model="test/model")
    assert "AGENTS.md" not in content


def test_build_system_instructions_with_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("Always answer in French\n")
    content = _service().build(model="test/model")
    assert "--- AGENTS.md ---" in content
    assert "Always answer in French" in content
    assert "--- end AGENTS.md ---" in content


def test_build_system_instructions_with_empty_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("")
    content = _service().build(model="test/model")
    assert "AGENTS.md" not in content


def test_build_layers_home_then_repo_guidance(tmp_path, monkeypatch):
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text("HOME GUIDANCE\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("REPO GUIDANCE\n", encoding="utf-8")
    monkeypatch.setattr("magecode.instructions.find_home", lambda: home)
    monkeypatch.chdir(repo)

    content = _service().build(model="test/model")
    assert content.index("HOME GUIDANCE") < content.index("REPO GUIDANCE")


def test_build_from_home_does_not_duplicate_guidance(tmp_path, monkeypatch):
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text("HOME GUIDANCE\n", encoding="utf-8")
    monkeypatch.setattr("magecode.instructions.find_home", lambda: home)
    monkeypatch.chdir(home)

    assert _service().build(model="test/model").count("HOME GUIDANCE") == 1


def test_build_ignores_unreadable_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").mkdir()
    assert "AGENTS.md" not in _service().build(model="test/model")


def test_count_tokens_positive():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello."},
    ]
    assert _service().count(messages) > 0


def test_count_tokens_increases_with_more_content():
    short = [{"role": "user", "content": "hi"}]
    long = [{"role": "user", "content": "hi " * 100}]
    assert _service().count(long) > _service().count(short)
