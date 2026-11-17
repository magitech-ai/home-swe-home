"""Tests for mini_claude.tools."""

from __future__ import annotations

import json

from mini_claude.tools import (
    CHAT_COMPLETION_TOOLS,
    execute_tool,
    grep_files,
    list_directory,
    read_file,
    run_command,
    tool_schemas,
    write_file,
)


def test_tool_schemas_match(CHAT_COMPLETION_TOOLS=CHAT_COMPLETION_TOOLS):
    assert tool_schemas() == CHAT_COMPLETION_TOOLS


def test_write_then_read_file(tmp_path):
    target = tmp_path / "note.txt"
    assert write_file(path=str(target), content="hello world") == (
        f"Wrote 11 characters to {target}."
    )
    assert read_file(path=str(target)) == "hello world"


def test_read_file_missing(tmp_path):
    result = execute_tool(
        "read_file", json.dumps({"path": str(tmp_path / "does-not-exist.txt")})
    )
    assert result.startswith("Error: FileNotFoundError: ")


def test_list_directory(tmp_path):
    (tmp_path / "a.txt").write_text("")
    (tmp_path / "sub").mkdir()
    result = list_directory(path=str(tmp_path))
    assert "a.txt" in result
    assert "sub/" in result


def test_list_directory_empty(tmp_path):
    assert list_directory(path=str(tmp_path)) == "(empty)"


def test_grep_files(tmp_path):
    (tmp_path / "sub").mkdir()  # non-file entry rglobbed during the walk
    (tmp_path / "one.txt").write_text("alpha beta\ngamma alpha\n")
    (tmp_path / "two.txt").write_text("no match here\n")
    result = grep_files(pattern=r"alpha", path=str(tmp_path))
    assert "one.txt:1: alpha beta" in result
    assert "one.txt:2: gamma alpha" in result


def test_grep_files_no_matches(tmp_path):
    (tmp_path / "one.txt").write_text("nothing\n")
    assert grep_files(pattern=r"zzz", path=str(tmp_path)) == "No matches."


def test_grep_files_skips_binary(tmp_path):
    text_file = tmp_path / "text.txt"
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01\x02\xff" * 100)
    text_file.write_text("visible line\n")
    expected = f"{text_file}:1: visible line"
    assert grep_files(pattern=r"visible", path=str(tmp_path)) == expected


def test_grep_files_caps_at_fifty_matches(tmp_path):
    content = "\n".join(f"match {i}" for i in range(60)) + "\n"
    (tmp_path / "many.txt").write_text(content)
    lines = grep_files(pattern=r"match", path=str(tmp_path)).splitlines()
    assert len(lines) == 50


def test_run_command_success():
    result = run_command(command="sh -c 'echo out; echo err >&2; exit 3'")
    assert "stdout:\nout\n" in result
    assert "stderr:\nerr\n" in result
    assert "exit code: 3" in result


def test_run_command_no_output():
    assert run_command(command="true") == "exit code: 0"


def test_run_command_timeout():
    arguments = json.dumps({"command": "sleep 10", "timeout": 1})
    result = execute_tool("run_command", arguments)
    assert result.startswith("Error: TimeoutExpired")


def test_execute_tool_unknown_tool():
    assert execute_tool("no_such_tool", "{}") == "Error: unknown tool 'no_such_tool'"


def test_execute_tool_bad_arguments():
    result = execute_tool("read_file", "{not json")
    assert result.startswith("Error: invalid tool arguments: ")


def test_execute_tool_type_error():
    result = execute_tool("read_file", "{}")
    assert result.startswith("Error: TypeError: ")


def test_execute_tool_returns_tool_result(tmp_path):
    target = tmp_path / "x.txt"
    result = execute_tool(
        "write_file", json.dumps({"path": str(target), "content": "hi"})
    )
    assert result == f"Wrote 2 characters to {target}."
    assert target.read_text() == "hi"
