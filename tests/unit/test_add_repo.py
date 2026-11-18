"""Tests for the map-driven add-repo tool."""

from __future__ import annotations

from types import SimpleNamespace

from anima import Context

from magecode.tools.add_repo import AddRepoService

_MAP = """## Other Repos

- **magecode** (agent): `../magecode`. Clone from
  <https://github.com/magitech-ai/magecode.git> if missing.
- **local-only** (no URL): `../local-only`.
"""


def _service(tmp_path, monkeypatch, *, home_exists=True):
    home = tmp_path / "agents-home"
    if home_exists:
        home.mkdir(exist_ok=True)
        (home / "AGENTS.md").write_text(_MAP, encoding="utf-8")
    monkeypatch.setattr(
        "magecode.tools.add_repo.find_home", lambda: home if home_exists else None
    )
    ctx = Context()
    ctx.use(AddRepoService)
    return ctx.add_repo, home  # type: ignore[return-value]


def test_no_home(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, monkeypatch, home_exists=False)
    assert "no agents-home" in service(ref="magecode")


def test_unmapped_repo(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, monkeypatch)
    assert "not in the home repo map" in service(ref="nope")


def test_existing_local_checkout(tmp_path, monkeypatch):
    service, home = _service(tmp_path, monkeypatch)
    (tmp_path / "magecode").mkdir()
    result = service(ref="magecode")
    assert "Resolved 'magecode'" in result
    assert str(tmp_path / "magecode") in result


def test_missing_checkout_needs_confirmation(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, monkeypatch)
    result = service(ref="magecode")
    assert "confirm=true" in result
    assert "magecode.git" in result


def test_missing_checkout_without_url(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, monkeypatch)
    assert "no clone URL" in service(ref="local-only")


def test_confirmed_clone(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, monkeypatch)
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("magecode.tools.add_repo.subprocess.run", fake_run)
    result = service(ref="magecode", confirm=True)
    assert "Cloned 'magecode'" in result
    assert calls[0][:2] == ["git", "clone"]


def test_failed_clone(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "magecode.tools.add_repo.subprocess.run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout="", stderr="permission denied"
        ),
    )
    assert "clone failed" in service(ref="magecode", confirm=True)
