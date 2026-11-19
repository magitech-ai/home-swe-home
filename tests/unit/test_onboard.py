"""Tests for home-checkout onboarding."""

from __future__ import annotations

from magecode import onboard


def test_needs_onboarding_true(monkeypatch):
    monkeypatch.setattr("magecode.onboard.find_home", lambda: None)
    assert onboard.needs_onboarding() is True


def test_needs_onboarding_false(monkeypatch, tmp_path):
    monkeypatch.setattr("magecode.onboard.find_home", lambda: tmp_path)
    assert onboard.needs_onboarding() is False


def test_scaffold_creates_starter_files(tmp_path):
    created = onboard.scaffold(tmp_path / "home")
    names = {path.relative_to(tmp_path / "home").as_posix() for path in created}
    assert {"AGENTS.md", "skills/README.md", "harness/systemprompt.md"} <= names
    assert "## Other Repos" in (tmp_path / "home" / "AGENTS.md").read_text()


def test_scaffold_preserves_existing_files(tmp_path):
    root = tmp_path / "home"
    root.mkdir()
    (root / "AGENTS.md").write_text("KEEP ME\n")
    (root / "harness").mkdir()
    (root / "harness" / "systemprompt.md").write_text("KEEP PROMPT\n")
    created = onboard.scaffold(root)
    assert not any(path.name in {"AGENTS.md", "systemprompt.md"} for path in created)
    assert (root / "AGENTS.md").read_text() == "KEEP ME\n"
    assert (root / "harness" / "systemprompt.md").read_text() == "KEEP PROMPT\n"


def test_provision_commands_include_gh_and_git(tmp_path):
    commands = onboard.provision_commands("org/agents-home", tmp_path)
    assert commands[0][:2] == ("gh", "auth")
    assert ("gh", "repo", "create", "org/agents-home", "--private") in commands
    assert any(command[:2] == ("git", "-C") for command in commands)


def test_run_wizard_declined_does_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("magecode.utils.home.CONFIG_PATH", tmp_path / "config.toml")
    seen: list[object] = []
    accepted = onboard.run_wizard(
        tmp_path / "home",
        "org/agents-home",
        confirm=lambda _: False,
        runner=seen.append,
    )
    assert accepted is False
    assert seen == []
    assert not (tmp_path / "home").exists()


def test_run_wizard_accepts_and_provisions(tmp_path, monkeypatch):
    monkeypatch.setattr("magecode.utils.home.CONFIG_PATH", tmp_path / "config.toml")
    seen: list[object] = []
    accepted = onboard.run_wizard(
        tmp_path / "home",
        "org/agents-home",
        confirm=lambda question: "org/agents-home" in question,
        runner=seen.append,
    )
    assert accepted is True
    assert len(seen) == len(onboard.provision_commands("org/agents-home", tmp_path))
    assert (tmp_path / "home" / "AGENTS.md").is_file()
    assert "org/agents-home" in (tmp_path / "config.toml").read_text()


def test_default_runner_invokes_subprocess(monkeypatch):
    seen: list[object] = []

    def fake_run(command, **kwargs):
        seen.append((command, kwargs))
        return object()

    monkeypatch.setattr("magecode.onboard.subprocess.run", fake_run)
    onboard.default_runner(("gh", "auth", "status"))
    assert seen[0][0] == ("gh", "auth", "status")
    assert seen[0][1]["check"] is True


def test_run_wizard_dry_run_skips_commands(tmp_path, monkeypatch):
    monkeypatch.setattr("magecode.utils.home.CONFIG_PATH", tmp_path / "config.toml")
    seen: list[object] = []
    accepted = onboard.run_wizard(
        tmp_path / "home",
        "org/home",
        confirm=lambda _: True,
        runner=seen.append,
        dry_run=True,
    )
    assert accepted is True
    assert seen == []
    assert (tmp_path / "home" / "AGENTS.md").is_file()
