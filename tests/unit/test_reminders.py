"""Tests for passive cross-session reminders in home-swe-home."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anima import Context

from home_swe_home import cli
from home_swe_home.instructions import InstructionsService
from home_swe_home.reminders import RemindersService
from home_swe_home.repl import run_repl
from home_swe_home.utils.reminders import (
    Reminder,
    discover_reminders,
    render_due_block,
    render_report,
    resolve_local_path,
)


def test_resolve_local_path_override_and_home_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "custom-reminders.toml"
    monkeypatch.setenv("AGENTS_REMINDERS_LOCAL_PATH", str(custom))
    assert resolve_local_path(tmp_path) == custom

    monkeypatch.delenv("AGENTS_REMINDERS_LOCAL_PATH", raising=False)
    assert resolve_local_path(tmp_path) == tmp_path / "reminders.local.toml"
    assert resolve_local_path(None) is None


def test_discover_reminders_classifies_all_states(tmp_path: Path) -> None:
    home_root = tmp_path / "home"
    home_root.mkdir()
    (home_root / "exists.txt").write_text("ok", encoding="utf-8")

    local_path = home_root / "reminders.local.toml"
    absent_path = tmp_path / "missing-dir"
    local_path.write_text(
        f"""
[reminders.due-now]
summary = "Immediate local task"

[reminders.overdue-one]
summary = "Overdue local task"
due = 2026-11-17
repo = "Pymordial"

[reminders.upcoming-one]
summary = "Future local task"
due = 2026-12-01

[reminders.resolved-absent]
summary = "Auto-resolved by absence"
done_when = {{ path_absent = "{absent_path.as_posix()}" }}
""",
        encoding="utf-8",
    )
    (home_root / "reminders.toml").write_text(
        """
[reminders.home-exists]
summary = "Auto-resolved by existence"
done_when = { path_exists = "exists.txt" }
""",
        encoding="utf-8",
    )

    items, warnings = discover_reminders(
        home_root=home_root,
        local_path=local_path,
        today=dt.date(2026, 11, 19),
    )
    assert warnings == []
    by_id = {r.id: r for r in items}
    assert by_id["due-now"].status == "due"
    assert by_id["due-now"].overdue_days == 0
    assert by_id["overdue-one"].status == "due"
    assert by_id["overdue-one"].overdue_days == 2
    assert by_id["upcoming-one"].status == "upcoming"
    assert by_id["resolved-absent"].status == "auto-resolved"
    assert by_id["home-exists"].status == "auto-resolved"


def test_discover_reminders_handles_missing_home_and_relative_without_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("AGENTS_REMINDERS_LOCAL_PATH", raising=False)
    assert discover_reminders(home_root=None) == ([], [])

    local_path = tmp_path / "local.toml"
    local_path.write_text(
        """
[reminders.rel-absent]
summary = "Relative without home"
done_when = { path_absent = "rel.txt" }

[reminders.rel-exists]
summary = "Relative exists without home"
done_when = { path_exists = "rel.txt" }
""",
        encoding="utf-8",
    )
    items, warnings = discover_reminders(
        home_root=None,
        local_path=local_path,
        today=dt.date(2026, 11, 19),
    )
    assert warnings == []
    assert all(r.status == "due" for r in items)


def test_discover_reminders_expands_tilde_and_warns_on_invalid_files(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "local.toml"
    local_path.write_text(
        """
[reminders.tilde-check]
summary = "Tilde expansion"
done_when = { path_absent = "~/nonexistent-okf-test-dir-xyz" }
""",
        encoding="utf-8",
    )
    items, warnings = discover_reminders(
        home_root=tmp_path, local_path=local_path, today=dt.date(2026, 11, 19)
    )
    assert warnings == []
    assert items[0].status == "auto-resolved"

    bad_cases = [
        "not = [valid",
        '["a"]',
        "other = 1\n",
        "reminders = 1\n",
        '[reminders."BAD ID"]\nsummary = "x"\n',
        "[reminders]\nbad = 1\n",
        '[reminders.bad]\nsummary = "x"\nextra = 1\n',
        '[reminders.bad]\nsummary = "line1\\nline2"\n',
        '[reminders.bad]\nsummary = "x"\ndue = "2026-11-19"\n',
        '[reminders.bad]\nsummary = "x"\ncreated = "2026-11-19"\n',
        '[reminders.bad]\nsummary = "x"\nrepo = ""\n',
        '[reminders.bad]\nsummary = "x"\ndone_when = 1\n',
        '[reminders.bad]\nsummary = "x"\ndone_when = { bad = "x" }\n',
        '[reminders.bad]\nsummary = "x"\ndone_when = { path_absent = "" }\n',
    ]
    for content in bad_cases:
        local_path.write_text(content, encoding="utf-8")
        items, warnings = discover_reminders(
            home_root=tmp_path, local_path=local_path, today=dt.date(2026, 11, 19)
        )
        assert items == []
        assert len(warnings) == 1

    home_root = tmp_path / "home"
    home_root.mkdir()
    (home_root / "reminders.toml").write_text(
        '[reminders.bad-home]\nsummary = "x"\n'
        'done_when = { path_absent = "~/secret" }\n',
        encoding="utf-8",
    )
    _, home_warnings = discover_reminders(
        home_root=home_root, local_path=tmp_path / "none.toml"
    )
    assert len(home_warnings) == 1


def test_render_due_block_and_report_formatting(tmp_path: Path) -> None:
    assert render_due_block([]) == ""
    assert render_report([], [], home_root=None) == "No reminders."

    many = [
        Reminder(
            id=f"r-{i}",
            scope="local",
            summary=f"Task {i}",
            due=dt.date(2026, 11, 18) if i == 0 else dt.date(2026, 11, 19),
            repo="Pymordial" if i == 0 else None,
            created=None,
            done_when={},
            status="due",
            overdue_days=1 if i == 0 else 0,
        )
        for i in range(12)
    ]
    block = render_due_block(many, cap=10)
    assert "--- Passive Reminders (due) ---" in block
    assert "overdue 1d" in block
    assert "... and 2 more due (/reminders)" in block

    report = render_report(
        [
            many[0],
            Reminder(
                id="up",
                scope="home",
                summary="Future",
                due=dt.date(2026, 12, 1),
                repo=None,
                created=None,
                done_when={},
                status="upcoming",
            ),
            Reminder(
                id="res",
                scope="local",
                summary="Gone",
                due=None,
                repo=None,
                created=None,
                done_when={},
                status="auto-resolved",
            ),
        ],
        ["warning: sample"],
        home_root=tmp_path,
    )
    assert "warning: sample" in report
    assert "Due:" in report
    assert "Upcoming:" in report
    assert "Auto-resolved (ready to prune):" in report
    assert "reminders.py done|snooze|prune" in report


def test_reminders_service_and_instructions_tail_injection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "reminders.local.toml"
    local_path.write_text(
        '[reminders.one]\nsummary = "Check v0.3"\n\n'
        '[reminders.two]\nsummary = "Resolved"\ndone_when = { path_absent = "'
        + (tmp_path / "absent").as_posix()
        + '" }\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENTS_REMINDERS_LOCAL_PATH", str(local_path))

    svc = RemindersService(Context())
    with patch("home_swe_home.reminders.find_home", return_value=None):
        assert "Check v0.3" in svc.due_block()
        assert "1 due, 1 auto-resolved" in svc.summary_line()
        assert svc.warnings() == []
        assert "Check v0.3" in svc.report()

    empty_path = tmp_path / "empty.toml"
    monkeypatch.setenv("AGENTS_REMINDERS_LOCAL_PATH", str(empty_path))
    svc_empty = RemindersService(Context())
    with patch("home_swe_home.reminders.find_home", return_value=None):
        assert svc_empty.summary_line() == ""

    inst = InstructionsService(Context())
    with patch.object(inst, "agents_md", return_value="AGENTS"):
        msg = inst.build(
            model="m",
            skills_catalog="SKILLS",
            reminders_block="REMINDERS",
        )
    assert msg.endswith("REMINDERS")


@pytest.mark.asyncio
async def test_repl_reminders_command_and_cli_headless_omission(
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock_ctx = MagicMock()
    mock_ctx.instructions.build.return_value = "SYS"
    mock_ctx.reminders.summary_line.return_value = "  reminders: 1 due (/reminders)"
    mock_ctx.reminders.report.return_value = "Due:\n  [local] r1  (due now)  Do thing"

    inputs = iter(["/reminders"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration as exc:
            raise EOFError from exc

    with patch("builtins.input", side_effect=fake_input):
        await run_repl(model="m", system_content="SYS", ctx=mock_ctx)

    captured = capsys.readouterr().out
    assert "reminders: 1 due (/reminders)" in captured
    assert "[local] r1" in captured

    mock_ctx.skills.catalog.return_value = ""
    mock_ctx.reminders.due_block.return_value = "DUE_BLOCK"
    with (
        patch("home_swe_home.cli.create_client"),
        patch("home_swe_home.cli.build_context", AsyncMock(return_value=mock_ctx)),
        patch("home_swe_home.cli._run_headless", AsyncMock(return_value=0)),
    ):
        rc = await cli._run_async(["-p", "hello"])
    assert rc == 0
    mock_ctx.instructions.build.assert_called_with(
        model=cli.DEFAULT_MODEL, skills_catalog="", reminders_block=""
    )
