"""Tests for mini_claude.instructions."""

from __future__ import annotations

from mini_claude.instructions import build_system_instructions, count_tokens


def test_build_system_instructions_contains_rules():
    content = build_system_instructions(model="test/model")
    assert "mini-claude" in content
    assert "Rules:" in content
    assert "Use tools" in content


def test_build_system_instructions_contains_system_line():
    content = build_system_instructions(model="test/model")
    assert "System:" in content
    assert "folder:" in content
    assert "date:" in content
    assert "model: test/model" in content


def test_build_system_instructions_no_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = build_system_instructions(model="test/model")
    assert "AGENTS.md" not in content


def test_build_system_instructions_with_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("Always answer in French\n")
    content = build_system_instructions(model="test/model")
    assert "--- AGENTS.md ---" in content
    assert "Always answer in French" in content
    assert "--- end AGENTS.md ---" in content


def test_build_system_instructions_with_empty_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("")
    content = build_system_instructions(model="test/model")
    assert "AGENTS.md" not in content


def test_count_tokens_positive():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello."},
    ]
    tokens = count_tokens(messages)
    assert tokens > 0


def test_count_tokens_increases_with_more_content():
    short = [{"role": "user", "content": "hi"}]
    long = [{"role": "user", "content": "hi " * 100}]
    assert count_tokens(long) > count_tokens(short)
