"""Tests for the map-driven add-repo tool definition."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from home_swe_home.tools.definitions import ADD_REPO

_MAP = """## Other Repos

- **home-swe-home** (agent): `../home-swe-home`. Clone from
  <https://github.com/magitech-ai/home-swe-home.git> if missing.
- **local-only** (no URL): `../local-only`.
"""


def _make_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text(_MAP, encoding="utf-8")
    (home / "skills").mkdir()
    monkeypatch.setenv("AGENTS_HOME_PATH", str(home))
    return home


def test_resolves_existing_repo(tmp_path: Path, monkeypatch) -> None:
    home = _make_home(tmp_path, monkeypatch)
    # The map says `../home-swe-home`, which resolves relative to the home dir.
    target = (home / ".." / "home-swe-home").resolve()
    target.mkdir(parents=True, exist_ok=True)

    result = ADD_REPO["execute"](
        {"ref": "home-swe-home"}, {"signal": None, "agent": None}
    )
    assert "Resolved" in result
    assert str(target) in result


def test_refuses_unknown_repo(tmp_path: Path, monkeypatch) -> None:
    _make_home(tmp_path, monkeypatch)

    result = ADD_REPO["execute"](
        {"ref": "nonexistent"}, {"signal": None, "agent": None}
    )
    assert "Error" in result
    assert "not in the home repo map" in result


def test_confirm_required_for_clone(tmp_path: Path, monkeypatch) -> None:
    _make_home(tmp_path, monkeypatch)

    result = ADD_REPO["execute"](
        {"ref": "home-swe-home", "confirm": False},
        {"signal": None, "agent": None},
    )
    assert "Confirm with confirm=true" in result


def test_clones_with_confirm(tmp_path: Path, monkeypatch) -> None:
    home = _make_home(tmp_path, monkeypatch)
    target = (home / ".." / "home-swe-home").resolve()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""
        result = ADD_REPO["execute"](
            {"ref": "home-swe-home", "confirm": True},
            {"signal": None, "agent": None},
        )

    assert "Cloned" in result
    assert str(target) in result


def test_no_home_configured(monkeypatch) -> None:
    monkeypatch.delenv("AGENTS_HOME_PATH", raising=False)
    monkeypatch.setattr(
        "home_swe_home.utils.home.find_home", lambda: None
    )

    result = ADD_REPO["execute"](
        {"ref": "anything"}, {"signal": None, "agent": None}
    )
    assert "Error" in result
    assert "no agents-home checkout" in result