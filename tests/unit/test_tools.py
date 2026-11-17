"""Tests for mini_claude.tools."""

from __future__ import annotations

import json
from unittest.mock import patch

from mini_claude.tools import (
    execute_tool,
    grep_files,
    list_directory,
    read_file,
    run_command,
    tool_schemas,
    web_search,
    write_file,
)


def test_tool_schemas_have_descriptions():
    schemas = tool_schemas()
    names = {s["function"]["name"] for s in schemas}
    expected = {
        "read_file",
        "write_file",
        "edit_file",
        "delete_file",
        "list_directory",
        "grep_files",
        "run_command",
        "web_search",
    }
    assert names == expected
    for schema in schemas:
        desc = schema["function"]["description"].lower()
        assert "error" in desc or "refused" in desc


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
    result = execute_tool("no_such_tool", "{}")
    assert result.startswith("Error: unknown tool 'no_such_tool'. Use one of: ")
    for name in sorted(
        {
            "read_file",
            "write_file",
            "edit_file",
            "delete_file",
            "list_directory",
            "grep_files",
            "run_command",
            "web_search",
        }
    ):
        assert name in result


def test_execute_tool_bad_arguments():
    result = execute_tool("read_file", "{not json")
    assert result.startswith("Error: invalid tool arguments: ")


def test_edit_file_replaces_exact_text(tmp_path):
    target = tmp_path / "script.txt"
    target.write_text("print('hello')\n")
    read_files = {str(target)}
    result = execute_tool(
        "edit_file",
        json.dumps({"path": str(target), "old_string": "hello", "new_string": "world"}),
        read_files=read_files,
    )
    assert result == f"Replaced the first occurrence of old_string in {target}."
    assert target.read_text() == "print('world')\n"


def test_edit_file_only_first_occurrence(tmp_path):
    target = tmp_path / "script.txt"
    target.write_text("hello hello\n")
    read_files = {str(target)}
    result = execute_tool(
        "edit_file",
        json.dumps({"path": str(target), "old_string": "hello", "new_string": "world"}),
        read_files=read_files,
    )
    assert "Replaced" in result
    assert target.read_text() == "world hello\n"


def test_edit_file_refuses_unread_file(tmp_path):
    target = tmp_path / "script.txt"
    target.write_text("print('hello')\n")
    result = execute_tool(
        "edit_file",
        json.dumps({"path": str(target), "old_string": "hello", "new_string": "world"}),
        read_files=set(),
    )
    assert result.startswith(f"Refused: '{target}' has not been read yet.")
    assert "Call read_file" in result
    assert target.read_text() == "print('hello')\n"  # unchanged


def test_edit_file_old_string_not_found(tmp_path):
    target = tmp_path / "script.txt"
    target.write_text("print('hello')\n")
    read_files = {str(target)}
    result = execute_tool(
        "edit_file",
        json.dumps(
            {"path": str(target), "old_string": "goodbye", "new_string": "world"}
        ),
        read_files=read_files,
    )
    assert result.startswith(f"Error: old_string not found in {target}.")
    assert "read_file" in result
    assert target.read_text() == "print('hello')\n"  # unchanged


def test_delete_file(tmp_path):
    target = tmp_path / "temp.txt"
    target.write_text("temporary\n")
    result = execute_tool("delete_file", json.dumps({"path": str(target)}))
    assert result == f"Deleted {target}."
    assert not target.exists()


def test_delete_file_nonexistent(tmp_path):
    target = tmp_path / "missing.txt"
    result = execute_tool("delete_file", json.dumps({"path": str(target)}))
    assert result.startswith("Error: FileNotFoundError: ")


def test_web_search_no_network(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"<html></html>"

    with patch("mini_claude.tools.urllib.request.urlopen", return_value=FakeResponse()):
        result = web_search(query="anything")
    assert result == "No web results found. Try rephrasing the query."


def test_web_search_returns_results(monkeypatch):
    html = (
        "<html><body>"
        '<a rel="nofollow" class="result__a" href="https://example.com/one">'
        "Result One</a>"
        '<a rel="nofollow" class="result__a" href="https://example.com/two">'
        "Result Two</a>"
        "</body></html>"
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return html.encode("utf-8")

    with patch("mini_claude.tools.urllib.request.urlopen", return_value=FakeResponse()):
        result = web_search(query="test")
    assert "Result One: https://example.com/one" in result
    assert "Result Two: https://example.com/two" in result


def test_web_search_network_error(monkeypatch):
    with patch(
        "mini_claude.tools.urllib.request.urlopen",
        side_effect=OSError("network down"),
    ):
        result = web_search(query="test")
    assert result.startswith("Error: web search failed: network down.")
    assert "retry the query" in result


def test_execute_tool_read_file_tracks_read_files(tmp_path):
    target = tmp_path / "track.txt"
    target.write_text("contents\n")
    read_files: set[str] = set()
    result = execute_tool(
        "read_file", json.dumps({"path": str(target)}), read_files=read_files
    )
    assert result == "contents\n"
    assert read_files == {str(target)}


def test_execute_tool_write_file_tracks_read_files(tmp_path):
    target = tmp_path / "track2.txt"
    read_files: set[str] = set()
    result = execute_tool(
        "write_file",
        json.dumps({"path": str(target), "content": "data"}),
        read_files=read_files,
    )
    assert result == f"Wrote 4 characters to {target}."
    assert read_files == {str(target)}
    assert target.read_text() == "data"


def test_execute_tool_read_file_without_read_files(tmp_path):
    target = tmp_path / "track.txt"
    target.write_text("contents\n")
    result = execute_tool("read_file", json.dumps({"path": str(target)}))
    assert result == "contents\n"


def test_execute_tool_write_file_without_read_files(tmp_path):
    target = tmp_path / "track2.txt"
    result = execute_tool(
        "write_file", json.dumps({"path": str(target), "content": "data"})
    )
    assert result.startswith("Wrote")
    assert target.read_text() == "data"


def test_web_search_many_results_triggers_break():
    links = "".join(
        f'<a rel="nofollow" class="result__a" href="https://example.com/{i}">'
        f"Result {i}</a>"
        for i in range(12)
    )
    html = f"<html><body>{links}</body></html>"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return html.encode("utf-8")

    with patch("mini_claude.tools.urllib.request.urlopen", return_value=FakeResponse()):
        result = web_search(query="test")
    lines = result.splitlines()
    assert len(lines) == 8  # capped at 8


def test_web_search_skips_empty_title():
    html = (
        "<html><body>"
        '<a rel="nofollow" class="result__a" href="https://example.com/one">'
        "  </a>"  # empty title
        '<a rel="nofollow" class="result__a" href="https://example.com/two">'
        "Real Result</a>"
        "</body></html>"
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return html.encode("utf-8")

    with patch("mini_claude.tools.urllib.request.urlopen", return_value=FakeResponse()):
        result = web_search(query="test")
    assert "Real Result: https://example.com/two" in result
    assert "https://example.com/one" not in result
