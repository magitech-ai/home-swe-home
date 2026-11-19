"""Pure helpers for agentskills.io-conformant skill discovery.

Discovery roots are ordered project → home → user. Aliases (symlinks) are
collapsed by resolved path before names are deduplicated by scope precedence,
with the shadowed path recorded in a warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_SCOPE_RANK = {"project": 3, "home": 2, "user": 1}


@dataclass(frozen=True)
class Skill:
    """One discovered skill: identity, source path, scope and invocation mode."""

    name: str
    description: str
    location: Path
    scope: str
    disabled: bool = False


def parse_skill(path: Path, scope: str) -> Skill | None:
    """Parse one ``SKILL.md`` leniently, returning ``None`` when unusable."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None

    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip("\"'")

    name = fields.get("name", "")
    description = fields.get("description", "")
    if not name or not description:
        return None
    return Skill(
        name=name,
        description=description,
        location=path.resolve(),
        scope=scope,
        disabled=fields.get("disable-model-invocation", "").lower() == "true",
    )


def discover_skills(roots: list[tuple[Path, str]]) -> tuple[list[Skill], list[str]]:
    """Discover skills from ``(root, scope)`` pairs, deduplicating aliases."""
    candidates: list[Skill] = []
    seen_paths: set[Path] = set()
    for root, scope in roots:
        if not root.is_dir():
            continue
        for directory in sorted(root.iterdir()):
            skill = parse_skill(directory / "SKILL.md", scope)
            if skill is None or skill.location in seen_paths:
                continue
            seen_paths.add(skill.location)
            candidates.append(skill)

    chosen: dict[str, Skill] = {}
    warnings: list[str] = []
    for skill in candidates:
        previous = chosen.get(skill.name)
        if previous is None:
            chosen[skill.name] = skill
        elif _SCOPE_RANK[skill.scope] >= _SCOPE_RANK[previous.scope]:
            chosen[skill.name] = skill
            warnings.append(
                f"skill '{skill.name}' shadowed {previous.location} "
                f"with {skill.location} ({skill.scope} scope)"
            )
        else:
            warnings.append(
                f"skill '{skill.name}' at {skill.location} was shadowed by "
                f"{previous.location} ({previous.scope} scope)"
            )
    return sorted(chosen.values(), key=lambda item: item.name), warnings


def render_catalog(skills: list[Skill]) -> str:
    """Build the always-on catalog; filtered skills are omitted entirely."""
    visible = [skill for skill in skills if not skill.disabled]
    if not visible:
        return ""
    lines = [
        "## Available skills",
        "",
        "When a task matches a skill's description, load its full instructions "
        "with `load_skill(name)` before acting. Resolve relative paths against "
        "the skill's directory. Skills not listed here are user-invoked and "
        "can be loaded explicitly with `/skill <name>`.",
        "",
    ]
    lines += [f"- **{skill.name}**: {skill.description}" for skill in visible]
    return "\n".join(lines)


def skill_body(skill: Skill) -> str:
    """Return the skill body wrapped in identifying tags (no frontmatter)."""
    text = skill.location.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        with_end = [
            i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        ]
        if with_end:
            start = with_end[0] + 1
    body = "\n".join(lines[start:]).strip()
    return f'<skill_content name="{skill.name}">\n{body}\n</skill_content>'
