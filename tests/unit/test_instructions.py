"""Tests for magecode.instructions (InstructionsService)."""

from __future__ import annotations

from anima import Context

from magecode.instructions import InstructionsService


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
