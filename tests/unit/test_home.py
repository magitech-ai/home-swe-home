"""Tests for agents-home resolution helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from magecode.utils import home as h


def _make_home(root: Path, name: str = "agents-home") -> Path:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "AGENTS.md").write_text("# Home\n", encoding="utf-8")
    (path / "skills").mkdir()
    return path


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(h, "CONFIG_PATH", path)
    monkeypatch.delenv("AGENTS_HOME_PATH", raising=False)
    return path


def test_load_config_missing(isolated_config):
    assert h.load_config() == {}


def test_load_config_invalid_toml(isolated_config):
    isolated_config.write_text("not = [valid", encoding="utf-8")
    assert h.load_config() == {}


def test_load_config_non_dict(isolated_config, monkeypatch):
    monkeypatch.setattr(h.tomllib, "load", lambda _handle: ["not", "a", "dict"])
    isolated_config.write_bytes(b"x = 1")
    assert h.load_config() == {}


def test_save_config_then_load(isolated_config, tmp_path):
    target = _make_home(tmp_path)
    path = h.save_config(home_path=target, repo="magitech-ai/agents-home")
    assert path == isolated_config
    assert h.load_config()["home"] == {
        "path": str(target.resolve()),
        "repo": "magitech-ai/agents-home",
    }


def test_save_config_without_repo(isolated_config, tmp_path):
    h.save_config(home_path=_make_home(tmp_path))
    assert "repo" not in h.load_config()["home"]


def test_trusted_projects_empty(isolated_config):
    assert h.trusted_projects() == ()


def test_trusted_projects_from_config(isolated_config):
    isolated_config.write_text(
        '[skills]\ntrusted_projects = ["/a/project", "/b/project"]\n', encoding="utf-8"
    )
    assert h.trusted_projects() == ("/a/project", "/b/project")


def test_trusted_projects_ignores_wrong_type(isolated_config):
    isolated_config.write_text(
        '[skills]\ntrusted_projects = "not a list"\n', encoding="utf-8"
    )
    assert h.trusted_projects() == ()


def test_looks_like_home_true(tmp_path):
    assert h.looks_like_home(_make_home(tmp_path))


def test_looks_like_home_missing_marker(tmp_path):
    path = tmp_path / "agents-home"
    path.mkdir()
    (path / "skills").mkdir()
    assert not h.looks_like_home(path)


def test_looks_like_home_missing_skills(tmp_path):
    path = tmp_path / "agents-home"
    path.mkdir()
    (path / "AGENTS.md").write_text("# Home\n", encoding="utf-8")
    assert not h.looks_like_home(path)


def test_looks_like_home_not_a_directory(tmp_path):
    assert not h.looks_like_home(tmp_path / "missing")


def test_find_home_from_config(isolated_config, tmp_path):
    target = _make_home(tmp_path)
    h.save_config(home_path=target)
    assert h.find_home() == target.resolve()


def test_find_home_ignores_invalid_config(isolated_config, tmp_path):
    isolated_config.write_text(
        '[home]\npath = "/definitely/not/a/home"\n', encoding="utf-8"
    )
    assert h.find_home(start=tmp_path) is None


def test_find_home_ignores_empty_and_non_string_config(isolated_config, tmp_path):
    isolated_config.write_text('[home]\npath = ""\nrepo = 7\n', encoding="utf-8")
    assert h.find_home(start=tmp_path) is None


def test_find_home_ignores_non_dict_config(isolated_config, tmp_path):
    isolated_config.write_text("home = 'not a table'\n", encoding="utf-8")
    assert h.find_home(start=tmp_path) is None


def test_find_home_env_override(isolated_config, tmp_path, monkeypatch):
    target = _make_home(tmp_path)
    monkeypatch.setenv("AGENTS_HOME_PATH", str(target))
    assert h.find_home() == target.resolve()


def test_find_home_ignores_invalid_env(isolated_config, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTS_HOME_PATH", str(tmp_path / "nope"))
    assert h.find_home(start=tmp_path) is None


def test_find_home_walk_up(isolated_config, tmp_path):
    target = _make_home(tmp_path)
    nested = target / "sub" / "deep"
    nested.mkdir(parents=True)
    assert h.find_home(start=nested) == target


def test_find_home_finds_sibling_checkout(isolated_config, tmp_path):
    target = _make_home(tmp_path)
    repo = tmp_path / "magecode"
    repo.mkdir()
    assert h.find_home(start=repo) == target.resolve()


def test_find_home_walk_up_ignores_bad_shape(isolated_config, tmp_path):
    bad = tmp_path / "agents-home"
    bad.mkdir()
    nested = bad / "sub"
    nested.mkdir()
    assert h.find_home(start=nested) is None


def test_find_home_default_location(isolated_config, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    target = _make_home(tmp_path, name=".agents/agents-home")
    assert h.find_home(start=tmp_path) == target.resolve()


def test_find_home_returns_none_when_unset(isolated_config, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert h.find_home(start=tmp_path) is None
