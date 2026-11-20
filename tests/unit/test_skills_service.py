"""Tests for the SkillsService component."""

from __future__ import annotations

from pathlib import Path

from anima import Context

from home_swe_home.skills import SkillsService


def _skill(root: Path, name: str, description: str, *, disabled: bool = False) -> None:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    flag = "disable-model-invocation: true\n" if disabled else ""
    content = (
        f"---\nname: {name}\ndescription: {description}\n"
        f"{flag}---\n\nBody for {name}.\n"
    )
    (path / "SKILL.md").write_text(content, encoding="utf-8")


def test_catalog_lists_visible_skills(tmp_path: Path, monkeypatch) -> None:
    user_skills = tmp_path / ".agents" / "skills"
    _skill(user_skills, "alpha", "Alpha skill")
    _skill(user_skills, "beta", "Beta skill", disabled=True)
    monkeypatch.setattr(
        "home_swe_home.skills.find_home", lambda: None
    )
    monkeypatch.setattr(
        "home_swe_home.utils.home.Path.home", lambda: tmp_path
    )

    ctx = Context()
    ctx.use(SkillsService)
    catalog = ctx.skills.catalog()

    assert "alpha" in catalog
    assert "Alpha skill" in catalog
    assert "beta" not in catalog


def test_load_returns_body_once(tmp_path: Path, monkeypatch) -> None:
    user_skills = tmp_path / ".agents" / "skills"
    _skill(user_skills, "alpha", "Alpha skill")
    monkeypatch.setattr(
        "home_swe_home.skills.find_home", lambda: None
    )
    monkeypatch.setattr(
        "home_swe_home.utils.home.Path.home", lambda: tmp_path
    )

    ctx = Context()
    ctx.use(SkillsService)

    first = ctx.skills.load("alpha")
    second = ctx.skills.load("alpha")

    assert "Body for alpha" in first
    assert "already in context" in second


def test_load_unknown_skill(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "home_swe_home.skills.find_home", lambda: None
    )
    monkeypatch.setattr(
        "home_swe_home.utils.home.Path.home", lambda: tmp_path
    )

    ctx = Context()
    ctx.use(SkillsService)

    result = ctx.skills.load("nonexistent")
    assert "Error" in result
    assert "not available" in result