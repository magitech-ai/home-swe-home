"""Tests for the issue-tracker contract helper."""

from __future__ import annotations

from magecode.utils.tracker import DEFAULT_LABELS, load_tracker


def test_default_when_no_config(tmp_path):
    tracker = load_tracker(tmp_path)
    assert tracker.kind == "github"
    assert tracker.cli == "gh"
    assert tracker.labels == DEFAULT_LABELS
    assert tracker.source == "builtin"


def test_repo_config_github(tmp_path):
    d = tmp_path / "docs" / "agents"
    d.mkdir(parents=True)
    (d / "issue-tracker.md").write_text("Use GitHub Issues via `gh` CLI.\n")
    assert load_tracker(tmp_path).source == "repo"
    assert load_tracker(tmp_path).kind == "github"


def test_repo_config_gitlab(tmp_path):
    d = tmp_path / "docs" / "agents"
    d.mkdir(parents=True)
    (d / "issue-tracker.md").write_text("Use `glab` for issues.\n")
    tracker = load_tracker(tmp_path)
    assert tracker.kind == "gitlab"
    assert tracker.cli == "glab"


def test_repo_config_local_markdown(tmp_path):
    d = tmp_path / "docs" / "agents"
    d.mkdir(parents=True)
    (d / "issue-tracker.md").write_text(
        "Store tickets under `.scratch/` as local markdown.\n"
    )
    tracker = load_tracker(tmp_path)
    assert tracker.kind == "local"
    assert tracker.cli == ""


def test_repo_labels_parsed_when_present(tmp_path):
    d = tmp_path / "docs" / "agents"
    d.mkdir(parents=True)
    (d / "issue-tracker.md").write_text(
        "Labels:\n- needs-triage\n- ready-for-agent\n- custom\n"
    )
    assert load_tracker(tmp_path).labels == ("needs-triage", "ready-for-agent")


def test_unreadable_config_falls_back_to_default(tmp_path):
    d = tmp_path / "docs" / "agents"
    d.mkdir(parents=True)
    (d / "issue-tracker.md").mkdir()
    assert load_tracker(tmp_path).source == "builtin"
