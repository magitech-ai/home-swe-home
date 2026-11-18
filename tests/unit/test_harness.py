"""Tests for the editable harness tree and its loader helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from anima import Service

from magecode.utils import harness as h
from magecode.utils.schema import service_schema


def test_harness_dir_defaults_to_packaged_tree(monkeypatch):
    monkeypatch.delenv("MAGECODE_HARNESS_DIR", raising=False)
    assert h.harness_dir() == h.DEFAULT_HARNESS_DIR


def test_harness_dir_honours_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MAGECODE_HARNESS_DIR", str(tmp_path))
    assert h.harness_dir() == tmp_path


def test_system_prompt_is_loaded_from_tree(monkeypatch, tmp_path):
    (tmp_path / "systemprompt.md").write_text("Custom rules.\n", encoding="utf-8")
    monkeypatch.setenv("MAGECODE_HARNESS_DIR", str(tmp_path))
    assert h.system_prompt() == "Custom rules.\n"


def test_read_harness_rejects_unknown_name():
    with pytest.raises(ValueError, match="not an editable harness file"):
        h.read_harness("../../secrets.txt")


def test_shipped_tool_guidance_is_empty_by_default(monkeypatch):
    monkeypatch.delenv("MAGECODE_HARNESS_DIR", raising=False)
    assert h.tool_guidance("read_file") == ""


def test_tool_guidance_parses_sections_and_skips_comments(monkeypatch, tmp_path):
    (tmp_path / "tool_guidance.md").write_text(
        "# Preamble\n"
        "\n"
        "## read_file\n"
        "# a comment inside the section\n"
        "Always read before editing.\n"
        "\n"
        "## run_command\n"
        "Check the exit code.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAGECODE_HARNESS_DIR", str(tmp_path))
    assert h.tool_guidance("read_file") == "Always read before editing."
    assert h.tool_guidance("run_command") == "Check the exit code."
    assert h.tool_guidance("unknown_tool") == ""


def test_service_schema_appends_guidance_to_description():
    class MyService(Service):
        """Do something."""

        def __init__(self, ctx):
            super().__init__(ctx, "my_tool")

        def __call__(self, *, value: str) -> str:
            return value

    schema = service_schema(MyService, guidance="Be careful.")
    assert schema["function"]["description"] == "Do something.\n\nBe careful."


def test_service_schema_guidance_without_docstring():
    class UndocumentedService(Service):
        def __init__(self, ctx):
            super().__init__(ctx, "undocumented")

        def __call__(self, *, value: str) -> str:
            return value

    schema = service_schema(UndocumentedService, guidance="Only guidance.")
    assert schema["function"]["description"] == "Only guidance."


def test_packaged_harness_files_are_real(monkeypatch):
    monkeypatch.delenv("MAGECODE_HARNESS_DIR", raising=False)
    root = Path(h.DEFAULT_HARNESS_DIR)
    assert (root / "systemprompt.md").is_file()
    assert (root / "tool_guidance.md").is_file()
    assert "You are magecode" in h.system_prompt()
