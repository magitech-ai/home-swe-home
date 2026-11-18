"""Tests for conformant skill discovery helpers."""

from __future__ import annotations

from pathlib import Path

from magecode.utils.skills import (
    Skill,
    discover_skills,
    parse_skill,
    render_catalog,
    skill_body,
)


def _skill_dir(
    root: Path, name: str, *, description: str = "Does a thing.", disabled: bool = False
) -> Path:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    flag = "disable-model-invocation: true\n" if disabled else ""
    content = (
        f"---\nname: {name}\ndescription: {description}\n"
        f"{flag}---\n\n# {name}\n\nBody text.\n"
    )
    (path / "SKILL.md").write_text(content, encoding="utf-8")
    return path


def test_parse_skill_missing_file(tmp_path):
    assert parse_skill(tmp_path / "nope" / "SKILL.md", "user") is None


def test_parse_skill_no_frontmatter(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("# Just a heading\n", encoding="utf-8")
    assert parse_skill(path, "user") is None


def test_parse_skill_unclosed_frontmatter(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("---\nname: x\ndescription: y\n", encoding="utf-8")
    assert parse_skill(path, "user") is None


def test_parse_skill_skips_lines_without_colon(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text(
        '---\nname: "x"\nno-colon-here\ndescription: "Does a thing."\n---\n',
        encoding="utf-8",
    )
    skill = parse_skill(path, "user")
    assert skill is not None
    assert skill.name == "x"
    assert skill.description == "Does a thing."
    assert skill.disabled is False


def test_parse_skill_missing_name_or_description(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("---\ndescription: only\n---\n", encoding="utf-8")
    assert parse_skill(path, "user") is None
    path.write_text("---\nname: only\n---\n", encoding="utf-8")
    assert parse_skill(path, "user") is None


def test_parse_skill_disabled_flag(tmp_path):
    directory = _skill_dir(tmp_path, "gated", disabled=True)
    skill = parse_skill(directory / "SKILL.md", "user")
    assert skill is not None and skill.disabled is True


def test_discover_skills_collapses_symlink_aliases(tmp_path):
    home = tmp_path / "home"
    user = tmp_path / "user"
    _skill_dir(home, "tdd")
    user.mkdir()
    (user / "tdd").symlink_to(home / "tdd", target_is_directory=True)

    skills, warnings = discover_skills([(home, "home"), (user, "user")])
    assert [skill.name for skill in skills] == ["tdd"]
    assert skills[0].scope == "home"
    assert warnings == []


def test_discover_skills_scope_precedence_and_warning(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    _skill_dir(home, "review", description="home version")
    _skill_dir(project, "review", description="project version")

    skills, warnings = discover_skills([(project, "project"), (home, "home")])
    assert skills[0].description == "project version"
    assert len(warnings) == 1
    assert "shadowed" in warnings[0]


def test_discover_skills_last_within_scope_wins(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _skill_dir(first, "review", description="older")
    _skill_dir(second, "review", description="newer")

    skills, warnings = discover_skills([(first, "user"), (second, "user")])
    assert skills[0].description == "newer"
    assert len(warnings) == 1


def test_discover_skills_lower_scope_is_shadowed(tmp_path):
    home = tmp_path / "home"
    user = tmp_path / "user"
    _skill_dir(home, "review", description="home version")
    _skill_dir(user, "review", description="user version")

    skills, warnings = discover_skills([(home, "home"), (user, "user")])
    assert skills[0].description == "home version"
    assert "was shadowed" in warnings[0]


def test_discover_skills_skips_missing_root_and_non_skills(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "notes.txt").write_text("not a skill\n")
    skills, warnings = discover_skills(
        [(tmp_path / "missing", "user"), (empty, "user")]
    )
    assert skills == [] and warnings == []


def test_render_catalog_empty():
    assert render_catalog([]) == ""


def test_render_catalog_hides_disabled_skills():
    skills = [
        Skill("visible", "A visible skill.", Path("/x/SKILL.md"), "home"),
        Skill("hidden", "A hidden skill.", Path("/y/SKILL.md"), "home", disabled=True),
    ]
    catalog = render_catalog(skills)
    assert "visible" in catalog and "hidden" not in catalog
    assert "load_skill(name)" in catalog


def test_skill_body_strips_frontmatter():
    directory = _skill_dir(Path("/tmp/opencode/skills-test"), "demo")
    skill = parse_skill(directory / "SKILL.md", "user")
    assert skill is not None
    body = skill_body(skill)
    assert body.startswith('<skill_content name="demo">')
    assert "name: demo" not in body
    assert "Body text." in body


def test_skill_body_without_frontmatter():
    directory = _skill_dir(Path("/tmp/opencode/skills-test"), "plain")
    path = directory / "SKILL.md"
    path.write_text("Just a body.\n", encoding="utf-8")
    skill = parse_skill(path, "user")
    assert skill is None
    bare = Skill("plain", "desc", path, "user")
    assert "Just a body." in skill_body(bare)


def test_skill_body_with_unclosed_frontmatter():
    directory = _skill_dir(Path("/tmp/opencode/skills-test"), "broken")
    path = directory / "SKILL.md"
    path.write_text("---\nname: broken\n", encoding="utf-8")
    bare = Skill("broken", "desc", path, "user")
    assert "name: broken" in skill_body(bare)
