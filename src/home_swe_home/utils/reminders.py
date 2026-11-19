"""Read-only parser and renderer for passive cross-session reminders.

Matches the two-scope TOML contract in ``agents-home/scripts/reminders.py``
(D-018):
  - ``local``: ``<agents-home>/reminders.local.toml`` (gitignored; override:
    ``AGENTS_REMINDERS_LOCAL_PATH``)
  - ``home``:  ``<agents-home>/reminders.toml``
"""

from __future__ import annotations

import datetime as dt
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ALLOWED_TOP_KEYS = frozenset({"reminders"})
ALLOWED_ENTRY_KEYS = frozenset({"summary", "due", "repo", "created", "done_when"})
ALLOWED_DONE_WHEN_KEYS = frozenset({"path_absent", "path_exists"})
DEFAULT_CAP = 10


@dataclass(frozen=True)
class Reminder:
    id: str
    scope: str
    summary: str
    due: dt.date | None
    repo: str | None
    created: dt.date | None
    done_when: dict[str, str]
    status: str  # "due" | "upcoming" | "auto-resolved"
    overdue_days: int = 0


def resolve_local_path(home_root: Path | None) -> Path | None:
    override = os.environ.get("AGENTS_REMINDERS_LOCAL_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    if home_root is None:
        return None
    return home_root / "reminders.local.toml"


def _resolve_condition_path(raw: str, home_root: Path | None) -> Path | None:
    if raw.startswith("~"):
        return Path(raw).expanduser()
    p = Path(raw)
    if p.is_absolute():
        return p
    if home_root is None:
        return None
    return home_root / p


def _evaluate_done_when(done_when: dict[str, str], home_root: Path | None) -> bool:
    if not done_when:
        return False
    checks: list[bool] = []
    if "path_absent" in done_when:
        target = _resolve_condition_path(done_when["path_absent"], home_root)
        if target is None:
            return False
        checks.append(not target.exists() and not target.is_symlink())
    if "path_exists" in done_when:
        target = _resolve_condition_path(done_when["path_exists"], home_root)
        if target is None:
            return False
        checks.append(target.exists())
    return bool(checks) and all(checks)


def _validate_scope(
    data: dict[str, Any],
    *,
    scope: str,
    path: Path,
) -> dict[str, dict[str, Any]]:
    extra_top = set(data.keys()) - ALLOWED_TOP_KEYS
    if extra_top:
        raise ValueError(
            f"{path}: unknown top-level key(s): {', '.join(sorted(extra_top))}"
        )
    raw_reminders = data.get("reminders", {})
    if not isinstance(raw_reminders, dict):
        raise ValueError(f"{path}: [reminders] must be a table")

    validated: dict[str, dict[str, Any]] = {}
    for rid, entry in raw_reminders.items():
        if not isinstance(rid, str) or not ID_RE.fullmatch(rid):
            raise ValueError(f"{path}: invalid reminder id {rid!r}")
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: reminders.{rid} must be a table")
        extra_keys = set(entry.keys()) - ALLOWED_ENTRY_KEYS
        if extra_keys:
            keys_str = ", ".join(sorted(extra_keys))
            raise ValueError(f"{path}: reminders.{rid}: unknown key(s): {keys_str}")
        summary = entry.get("summary")
        if (
            not isinstance(summary, str)
            or not summary.strip()
            or "\n" in summary
            or "\r" in summary
        ):
            raise ValueError(
                f"{path}: reminders.{rid}.summary must be a non-empty single-line str"
            )
        due = entry.get("due")
        if due is not None and (
            not isinstance(due, dt.date) or isinstance(due, dt.datetime)
        ):
            raise ValueError(f"{path}: reminders.{rid}.due must be a TOML date")
        created = entry.get("created")
        if created is not None and (
            not isinstance(created, dt.date) or isinstance(created, dt.datetime)
        ):
            raise ValueError(f"{path}: reminders.{rid}.created must be a TOML date")
        repo = entry.get("repo")
        if repo is not None and (not isinstance(repo, str) or not repo.strip()):
            raise ValueError(f"{path}: reminders.{rid}.repo must be a non-empty string")
        done_when = entry.get("done_when", {})
        if not isinstance(done_when, dict):
            raise ValueError(f"{path}: reminders.{rid}.done_when must be a table")
        extra_dw = set(done_when.keys()) - ALLOWED_DONE_WHEN_KEYS
        if extra_dw:
            dw_keys = ", ".join(sorted(extra_dw))
            raise ValueError(
                f"{path}: reminders.{rid}.done_when: unknown key(s): {dw_keys}"
            )
        norm_dw: dict[str, str] = {}
        for k, v in done_when.items():
            if not isinstance(v, str) or not v.strip():
                raise ValueError(
                    f"{path}: reminders.{rid}.done_when.{k} must be a non-empty string"
                )
            if scope == "home" and (v.startswith("~") or Path(v).is_absolute()):
                raise ValueError(
                    f"{path}: reminders.{rid}.done_when.{k} must be repo-relative"
                )
            norm_dw[k] = v.strip()

        validated[rid] = {
            "summary": summary.strip(),
            "due": due,
            "repo": repo.strip() if isinstance(repo, str) else None,
            "created": created,
            "done_when": norm_dw,
        }
    return validated


def discover_reminders(
    *,
    home_root: Path | None,
    local_path: Path | None = None,
    today: dt.date | None = None,
) -> tuple[list[Reminder], list[str]]:
    """Load local and shared home reminders without raising on malformed files."""
    ref_day = today or dt.date.today()
    lpath = local_path if local_path is not None else resolve_local_path(home_root)
    sources: list[tuple[str, Path]] = []
    if lpath is not None:
        sources.append(("local", lpath))
    if home_root is not None:
        sources.append(("home", home_root / "reminders.toml"))

    items: list[Reminder] = []
    warnings: list[str] = []

    for scope, path in sources:
        if not path.is_file():
            continue
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
            entries = _validate_scope(raw, scope=scope, path=path)
        except (
            OSError,
            UnicodeDecodeError,
            tomllib.TOMLDecodeError,
            ValueError,
        ) as exc:
            warnings.append(f"warning: {exc}")
            continue

        for rid, item in sorted(entries.items()):
            dw = item["done_when"]
            due: dt.date | None = item["due"]
            if _evaluate_done_when(dw, home_root):
                status = "auto-resolved"
                overdue = 0
            elif due is None or due <= ref_day:
                status = "due"
                overdue = (
                    (ref_day - due).days if due is not None and due < ref_day else 0
                )
            else:
                status = "upcoming"
                overdue = 0
            items.append(
                Reminder(
                    id=rid,
                    scope=scope,
                    summary=item["summary"],
                    due=due,
                    repo=item["repo"],
                    created=item["created"],
                    done_when=dw,
                    status=status,
                    overdue_days=overdue,
                )
            )
    return items, warnings


def _format_tag(r: Reminder) -> str:
    if r.status == "auto-resolved":
        return "auto-resolved"
    if r.overdue_days > 0:
        return f"overdue {r.overdue_days}d"
    if r.due is not None:
        return f"due {r.due.isoformat()}"
    return "due now"


def render_due_block(items: list[Reminder], *, cap: int = DEFAULT_CAP) -> str:
    """Render due/overdue reminders for interactive session instructions."""
    due_items = [r for r in items if r.status == "due"]
    if not due_items:
        return ""
    lines = ["--- Passive Reminders (due) ---"]
    for r in due_items[:cap]:
        repo_part = f" [{r.repo}]" if r.repo else ""
        lines.append(f"- [{r.scope}]{repo_part} {r.id} ({_format_tag(r)}): {r.summary}")
    if len(due_items) > cap:
        lines.append(f"- ... and {len(due_items) - cap} more due (/reminders)")
    lines.append("--- end Passive Reminders ---")
    return "\n".join(lines)


def render_report(
    items: list[Reminder],
    warnings: list[str],
    *,
    home_root: Path | None,
) -> str:
    """Render full read-only output for the REPL ``/reminders`` command."""
    if not items and not warnings:
        return "No reminders."
    lines: list[str] = []
    for warning in warnings:
        lines.append(warning)
    for status, heading in (
        ("due", "Due:"),
        ("upcoming", "Upcoming:"),
        ("auto-resolved", "Auto-resolved (ready to prune):"),
    ):
        group = [r for r in items if r.status == status]
        if not group:
            continue
        lines.append(heading)
        for r in group:
            repo_part = f"[{r.repo}] " if r.repo else ""
            lines.append(
                f"  [{r.scope}]{repo_part} {r.id}  ({_format_tag(r)})  {r.summary}"
            )
    script = (
        f"{home_root / 'scripts' / 'reminders.py'}"
        if home_root is not None
        else "scripts/reminders.py"
    )
    lines.append(f"Manage: uv run --no-project python {script} done|snooze|prune ...")
    return "\n".join(lines)
