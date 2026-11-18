"""Tests for tool-result secret redaction."""

from __future__ import annotations

from anima import Context

from magecode.tools.executor import ToolService
from magecode.utils.secrets import redact, secret_values


def test_secret_values_reads_env(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secret")
    assert "nvapi-secret" in secret_values()


def test_redact_replaces_known_secret(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secret")
    assert redact("NVIDIA_API_KEY=nvapi-secret") == "NVIDIA_API_KEY=<redacted>"


def test_redact_leaves_ordinary_text(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    assert redact("nothing to hide") == "nothing to hide"


def test_tool_result_is_redacted(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secret")

    class LeakyService:
        name = "leaky"

        def __call__(self):
            return "NVIDIA_API_KEY=nvapi-secret"

    ctx = Context()
    ctx.use(ToolService)
    ctx.reflect.provide("leaky", LeakyService())
    assert ctx.tools.execute("leaky", "{}") == "NVIDIA_API_KEY=<redacted>"
