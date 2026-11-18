"""Pure helpers for locating the agents-home checkout.

Resolution order: config file, ``AGENTS_HOME_PATH``, name-based walk-up from
cwd, then the conventional ``~/.agents/agents-home`` location. The checkout may
live on a different filesystem from the config, so config stores an absolute
path and never a relative one.
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

CONFIG_PATH = Path.home() / ".agents" / "magecode" / "config.toml"
HOME_NAME = "agents-home"


def config_path() -> Path:
    """Return the magecode config path (overridable in tests)."""
    return CONFIG_PATH


def load_config() -> dict:
    """Read the config, returning an empty dict when absent or unparseable."""
    try:
        with config_path().open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(*, home_path: Path, repo: str = "") -> Path:
    """Write the authoritative home path and optional repo identity."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[home]", f"path = {json.dumps(str(Path(home_path).resolve()))}"]
    if repo:
        lines.append(f"repo = {json.dumps(repo)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def looks_like_home(path: Path) -> bool:
    """Whether *path* has the shape of an agents-home checkout."""
    return (
        path.is_dir() and (path / "AGENTS.md").is_file() and (path / "skills").is_dir()
    )


def find_home(start: Path | None = None) -> Path | None:
    """Return the active agents-home checkout, or ``None`` when unset."""
    configured = load_config().get("home")
    if isinstance(configured, dict):
        value = configured.get("path")
        if isinstance(value, str) and value:
            candidate = Path(value).expanduser()
            if looks_like_home(candidate):
                return candidate.resolve()

    override = os.environ.get("AGENTS_HOME_PATH")
    if override:
        candidate = Path(override).expanduser()
        if looks_like_home(candidate):
            return candidate.resolve()

    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        if directory.name == HOME_NAME and looks_like_home(directory):
            return directory
        sibling = directory / HOME_NAME
        if looks_like_home(sibling):
            return sibling.resolve()

    default = Path.home() / ".agents" / HOME_NAME
    if looks_like_home(default):
        return default.resolve()
    return None
