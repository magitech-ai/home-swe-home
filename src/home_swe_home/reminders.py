"""RemindersService: read-only discovery of passive cross-session reminders."""

from __future__ import annotations

from pathlib import Path

from animas import Context, Service

from .utils.home import find_home
from .utils.reminders import (
    Reminder,
    discover_reminders,
    render_due_block,
    render_report,
)


class RemindersService(Service):
    """Mounted as ``ctx.reminders``; surfaces due passive reminders."""

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "reminders")
        self._items: list[Reminder] | None = None
        self._warnings: list[str] = []
        self._home_root: Path | None = None

    def _ensure(self) -> None:
        if self._items is None:
            self._home_root = find_home()
            self._items, self._warnings = discover_reminders(
                home_root=self._home_root,
            )

    def due_block(self) -> str:
        """Return compact prompt block of due reminders (empty when none)."""
        self._ensure()
        return render_due_block(self._items or [])

    def report(self) -> str:
        """Return full read-only report for ``/reminders``."""
        self._ensure()
        return render_report(
            self._items or [], self._warnings, home_root=self._home_root
        )

    def summary_line(self) -> str:
        """Return 1-line startup banner when due or auto-resolved items exist."""
        self._ensure()
        items = self._items or []
        due_count = sum(1 for r in items if r.status == "due")
        resolved_count = sum(1 for r in items if r.status == "auto-resolved")
        parts: list[str] = []
        if due_count:
            parts.append(f"{due_count} due")
        if resolved_count:
            parts.append(f"{resolved_count} auto-resolved")
        if not parts:
            return ""
        return f"  reminders: {', '.join(parts)} (/reminders)"

    def warnings(self) -> list[str]:
        """Return any parse/validation warnings from discovery."""
        self._ensure()
        return list(self._warnings)
