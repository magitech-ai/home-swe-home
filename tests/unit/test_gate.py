"""Tests for the fail-closed review kill switch."""

from __future__ import annotations

import pytest

from home_swe_home import gate


@pytest.mark.parametrize("value", [None, "", "false", "TRUE", "1", "yes"])
def test_kill_switch_fails_closed(value: str | None) -> None:
    with pytest.raises(RuntimeError, match="disabled by kill switch"):
        gate.check_review_enabled(value)


def test_explicit_true_enables() -> None:
    gate.check_review_enabled("true")


def test_main_fails_closed(monkeypatch, capsys) -> None:
    monkeypatch.delenv(gate.KILL_SWITCH_ENV, raising=False)
    assert gate.main([]) == 2
    assert "disabled by kill switch" in capsys.readouterr().err


def test_main_succeeds_when_enabled(monkeypatch, capsys) -> None:
    monkeypatch.setenv(gate.KILL_SWITCH_ENV, "true")
    assert gate.main([]) == 0
    assert "review enabled" in capsys.readouterr().out
