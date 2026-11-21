"""Tests for the ``hsh-improve`` CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from home_swe_home import improve_cli
from home_swe_home.eval import EvalResult, Task
from home_swe_home.orchestrate import CycleReport
from home_swe_home.utils.selection import Selection


def _base(tmp_path: Path) -> Path:
    base = tmp_path / "harness"
    base.mkdir()
    (base / "systemprompt.md").write_text("You are an agent.", encoding="utf-8")
    (base / "tool_guidance.md").write_text("## read_file\nRead.", encoding="utf-8")
    return base


def _report(*, adopted: bool = True) -> CycleReport:
    base = EvalResult("base", 1, 6, 10, ())
    candidate = EvalResult("candidate", 1, 9, 10, ())
    return CycleReport(
        task="my task",
        domain="coding",
        scores={"base": 0.6, "candidate": 0.9},
        selection=Selection(
            "candidate" if adopted else None,
            "highest pass rate 0.90" if adopted else "no strict winner at 0.90",
        ),
        adopted=adopted,
        adopted_dir=Path("/tmp/adopted") if adopted else None,
        base=base,
        candidate=candidate,
        rejection="" if adopted else "no strict winner at 0.90",
        proposals=1,
    )


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


def test_parser_defaults() -> None:
    args = improve_cli.build_parser().parse_args(["my task"])
    assert args.task == "my task"
    assert args.domain == "general"
    assert args.trials == 1
    assert args.quiet is False


def test_parser_options() -> None:
    args = improve_cli.build_parser().parse_args(
        [
            "task",
            "--domain",
            "coding",
            "--trials",
            "3",
            "--work-dir",
            "/tmp/w",
            "--library-root",
            "/tmp/l",
            "--out",
            "/tmp/report.json",
            "--quiet",
        ]
    )
    assert args.domain == "coding"
    assert args.trials == 3
    assert args.work_dir == Path("/tmp/w")
    assert args.library_root == Path("/tmp/l")
    assert args.out == Path("/tmp/report.json")
    assert args.quiet is True


# ---------------------------------------------------------------------------
# path resolvers
# ---------------------------------------------------------------------------


def test_base_dir_explicit() -> None:
    assert improve_cli._base_dir(Path("/tmp/base")) == Path("/tmp/base")


def test_base_dir_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_HARNESS_DIR", str(tmp_path))
    assert improve_cli._base_dir(None) == tmp_path


def test_base_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_HARNESS_DIR", raising=False)
    assert improve_cli._base_dir(None) == improve_cli.DEFAULT_HARNESS_DIR


def test_work_dir_explicit() -> None:
    assert improve_cli._work_dir(Path("/tmp/w")) == Path("/tmp/w")


def test_work_dir_default() -> None:
    assert improve_cli._work_dir(None) == Path(".hsh-improve")


# ---------------------------------------------------------------------------
# config errors (fail fast)
# ---------------------------------------------------------------------------


def test_main_requires_proposer_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_PROPOSER_MODEL", raising=False)
    assert improve_cli.main(["task"]) == 2
    assert "HOME_SWE_HOME_PROPOSER_MODEL" in capsys.readouterr().err


def test_main_rejects_zero_trials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_PROPOSER_MODEL", "some/model")
    assert improve_cli.main(["task", "--trials", "0"]) == 2
    assert "--trials must be at least 1" in capsys.readouterr().err


def test_main_rejects_missing_base_dir(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_PROPOSER_MODEL", "some/model")
    assert improve_cli.main(["task", "--base-dir", str(tmp_path / "missing")]) == 2
    assert "harness directory not found" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main success / rejection
# ---------------------------------------------------------------------------


def test_main_prints_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    base = _base(tmp_path)
    monkeypatch.setenv("HOME_SWE_HOME_PROPOSER_MODEL", "some/model")

    def fake_run_cycle(**_kwargs: Any) -> CycleReport:
        return _report()

    monkeypatch.setattr(improve_cli, "run_cycle", fake_run_cycle)
    monkeypatch.setattr(improve_cli, "build_proposer", lambda _ask: object())
    monkeypatch.setattr(improve_cli, "default_ask", lambda _prompt: "")

    assert (
        improve_cli.main(
            ["task", "--base-dir", str(base), "--work-dir", str(tmp_path / "w")]
        )
        == 0
    )
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["adopted"] is True
    assert payload["winner"] == "candidate"
    assert payload["scores"]["candidate"] == 0.9


def test_main_writes_report_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = _base(tmp_path)
    monkeypatch.setenv("HOME_SWE_HOME_PROPOSER_MODEL", "some/model")
    monkeypatch.setattr(improve_cli, "run_cycle", lambda **_kw: _report())
    monkeypatch.setattr(improve_cli, "build_proposer", lambda _ask: object())
    monkeypatch.setattr(improve_cli, "default_ask", lambda _prompt: "")

    out = tmp_path / "reports" / "report.json"
    assert (
        improve_cli.main(
            [
                "task",
                "--base-dir",
                str(base),
                "--work-dir",
                str(tmp_path / "w"),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    # Path stringification is platform-specific (POSIX '/tmp/...' vs Windows
    # '\\tmp\\...'), so compare against the platform's own rendering.
    assert payload["adopted_dir"] == str(Path("/tmp/adopted"))


def test_main_reports_non_adoption(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    base = _base(tmp_path)
    monkeypatch.setenv("HOME_SWE_HOME_PROPOSER_MODEL", "some/model")
    monkeypatch.setattr(improve_cli, "run_cycle", lambda **_kw: _report(adopted=False))
    monkeypatch.setattr(improve_cli, "build_proposer", lambda _ask: object())
    monkeypatch.setattr(improve_cli, "default_ask", lambda _prompt: "")

    assert (
        improve_cli.main(
            [
                "task",
                "--base-dir",
                str(base),
                "--work-dir",
                str(tmp_path / "w"),
                "--quiet",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["adopted"] is False
    assert "no strict winner" in payload["rejection"]


def test_main_passes_all_options_to_cycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = _base(tmp_path)
    monkeypatch.setenv("HOME_SWE_HOME_PROPOSER_MODEL", "some/model")
    captured: dict[str, Any] = {}

    def fake_run_cycle(**kwargs: Any) -> CycleReport:
        captured.update(kwargs)
        return _report()

    monkeypatch.setattr(improve_cli, "run_cycle", fake_run_cycle)
    monkeypatch.setattr(improve_cli, "build_proposer", lambda _ask: object())
    monkeypatch.setattr(improve_cli, "default_ask", lambda _prompt: "")

    improve_cli.main(
        [
            "task",
            "--domain",
            "coding",
            "--trials",
            "3",
            "--base-dir",
            str(base),
            "--work-dir",
            str(tmp_path / "w"),
            "--library-root",
            str(tmp_path / "lib"),
            "--quiet",
        ]
    )
    assert captured["task"] == "task"
    assert captured["domain"] == "coding"
    assert captured["trials"] == 3
    assert captured["library_root"] == tmp_path / "lib"
    assert len(captured["tasks"]) == len(improve_cli.HARD_TASKS)
    assert all(isinstance(t, Task) for t in captured["tasks"])


# ---------------------------------------------------------------------------
# event printing
# ---------------------------------------------------------------------------


def test_on_event_quiet(capsys: pytest.CaptureFixture[str]) -> None:
    improve_cli._on_event("progress", quiet=True)
    assert capsys.readouterr().err == ""


def test_on_event_verbose(capsys: pytest.CaptureFixture[str]) -> None:
    improve_cli._on_event("progress", quiet=False)
    assert "progress" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# report rendering
# ---------------------------------------------------------------------------


def test_report_payload_without_candidate() -> None:
    report = _report()
    object.__setattr__(report, "candidate", None)
    payload = improve_cli._report_payload(report)
    assert payload["candidate"] is None


def test_report_payload_without_adopted_dir() -> None:
    report = _report(adopted=False)
    payload = improve_cli._report_payload(report)
    assert payload["adopted_dir"] is None


def test_main_handles_proposal_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A ProposalError from the loop is a clean config/data error, not a crash."""
    from home_swe_home.orchestrate import ProposalError

    base = _base(tmp_path)
    monkeypatch.setenv("HOME_SWE_HOME_PROPOSER_MODEL", "some/model")

    def raise_error(**_kwargs: Any) -> CycleReport:
        raise ProposalError("proposer did not return JSON")

    monkeypatch.setattr(improve_cli, "run_cycle", raise_error)
    monkeypatch.setattr(improve_cli, "build_proposer", lambda _ask: object())
    monkeypatch.setattr(improve_cli, "default_ask", lambda _prompt: "")

    assert (
        improve_cli.main(
            ["task", "--base-dir", str(base), "--work-dir", str(tmp_path / "w")]
        )
        == 2
    )
    assert "proposer did not return JSON" in capsys.readouterr().err
