"""SkillsService: discovery, catalog and on-demand activation of skills."""

from __future__ import annotations

from pathlib import Path

from anima import Context, Service

from .utils.home import find_home, trusted_projects
from .utils.skills import Skill, discover_skills, render_catalog, skill_body


class SkillsService(Service):
    """Mounted as ``ctx.skills``; owns the session's skill catalog."""

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "skills")
        self._skills: list[Skill] | None = None
        self._warnings: list[str] = []
        self._activated: set[str] = set()

    def _roots(self) -> list[tuple[Path, str]]:
        roots: list[tuple[Path, str]] = []
        cwd = Path.cwd()
        if str(cwd) in trusted_projects():
            roots.append((cwd / ".agents" / "skills", "project"))
        home = find_home()
        if home is not None:
            roots.append((home / "skills", "home"))
        roots.append((Path.home() / ".agents" / "skills", "user"))
        return roots

    def _ensure(self) -> None:
        if self._skills is None:
            self._skills, self._warnings = discover_skills(self._roots())

    def catalog(self) -> str:
        """Return the always-on catalog of model-invokable skills."""
        self._ensure()
        return render_catalog(self._skills or [])

    def warnings(self) -> list[str]:
        """Return shadowing warnings from discovery."""
        self._ensure()
        return list(self._warnings)

    def load(self, name: str) -> str:
        """Load one skill body on demand; dedupe repeat activations."""
        self._ensure()
        for skill in self._skills or []:
            if skill.name == name:
                if name in self._activated:
                    return f"Skill '{name}' is already in context."
                self._activated.add(name)
                return skill_body(skill)
        return f"Error: skill '{name}' is not available."
