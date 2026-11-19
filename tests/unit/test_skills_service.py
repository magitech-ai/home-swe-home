"""Tests for the SkillsService component."""

from __future__ import annotations

from pathlib import Path

from anima import Context

from home_swe_home.skills import SkillsService
from home_swe_home.tools.load_skill import LoadSkillService


def _skill(root: Path, name: str, description: str, *, disabled: bool = False) -> None:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    flag = "disable-model-invocation: true\n" if disabled else ""
    content = (
        f"---\nname: {name}\ndescription: {description}\n"
        f"{flag}---\n\nBody for {name}.\n"
    )
    (path / "SKILL.md").write_text(content, encoding="utf-8")


def _service(monkeypatch, tmp_path, *, trusted=()):
    user = tmp_path / "userhome"
    user.mkdir()
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text("# Home\n")
    (home / "skills").mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / ".agents" / "skills").mkdir(parents=True)
    _skill(home / "skills", "tdd", "Red-green testing.")
    _skill(home / "skills", "gated", "User only.", disabled=True)
    _skill(user / ".agents" / "skills", "review", "Review a diff.")
    _skill(project / ".agents" / "skills", "local", "Project-local skill.")

    monkeypatch.setattr("home_swe_home.skills.find_home", lambda: home)
    monkeypatch.setattr("home_swe_home.skills.trusted_projects", lambda: trusted)
    monkeypatch.setattr(Path, "home", lambda: user)
    monkeypatch.chdir(project)
    ctx = Context()
    ctx.use(SkillsService)
    return ctx


def test_catalog_lists_model_invokable_skills(monkeypatch, tmp_path):
    skills = _service(monkeypatch, tmp_path).skills
    catalog = skills.catalog()
    assert "**tdd**" in catalog
    assert "**review**" in catalog
    assert "gated" not in catalog
    assert "local" not in catalog  # project scope is untrusted


def test_project_skills_require_trust(monkeypatch, tmp_path):
    ctx = _service(monkeypatch, tmp_path, trusted=(str(tmp_path / "project"),))
    skills = ctx.skills
    assert "**local**" in skills.catalog()


def test_load_returns_body_and_dedupes(monkeypatch, tmp_path):
    skills = _service(monkeypatch, tmp_path).skills
    body = skills.load("tdd")
    assert "Body for tdd." in body
    assert "already in context" in skills.load("tdd")


def test_load_unknown_skill(monkeypatch, tmp_path):
    assert "not available" in _service(monkeypatch, tmp_path).skills.load("missing")


def test_load_user_invoked_skill_explicitly(monkeypatch, tmp_path):
    assert "Body for gated." in _service(monkeypatch, tmp_path).skills.load("gated")


def test_warnings_reported(monkeypatch, tmp_path):
    skills = _service(monkeypatch, tmp_path).skills
    assert isinstance(skills.warnings(), list)


def test_roots_without_home(monkeypatch, tmp_path):
    monkeypatch.setattr("home_swe_home.skills.find_home", lambda: None)
    monkeypatch.setattr("home_swe_home.skills.trusted_projects", lambda: ())
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    ctx = Context()
    ctx.use(SkillsService)
    assert "**" not in ctx.skills.catalog()  # type: ignore[attr-defined]


def test_load_skill_tool_uses_service(monkeypatch, tmp_path):
    ctx = _service(monkeypatch, tmp_path)
    ctx.use(LoadSkillService)
    assert "Body for tdd." in ctx.load_skill(name="tdd")
