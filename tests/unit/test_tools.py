"""Tests for magecode.tools."""

from __future__ import annotations

import json
import os
import subprocess
from unittest.mock import patch

from magecode.tools import (
    _TOOLS,
    _python_type_to_json_schema_type,
    code_metrics,
    execute_tool,
    find_duplicates,
    generate_docs,
    get_module_mtime,
    grep_files,
    list_directory,
    read_file,
    run_command,
    tool,
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
        "reload_module",
        "code_metrics",
        "find_duplicates",
        "generate_docs",
    }
    assert names == expected
    for schema in schemas:
        desc = schema["function"]["description"]
        assert desc, f"Schema for {schema['function']['name']} has no description"


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


def test_run_command_host_default(monkeypatch):
    """run_command runs on the host by default (no sandbox)."""
    monkeypatch.delenv("MAGECODE_SANDBOX", raising=False)
    calls = []

    def fake_run(cmd, *, capture_output, text, timeout):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "out\n", "err\n")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = run_command(command="echo out; echo err >&2", timeout=10)
    assert "stdout:\nout\n" in result
    assert "stderr:\nerr\n" in result
    assert "exit code: 0" in result
    assert calls[0] == ["echo", "out;", "echo", "err", ">&2"]


def test_run_command_host_default_uses_subprocess(monkeypatch):
    """Host execution delegates to subprocess.run with shlex-split args."""
    monkeypatch.delenv("MAGECODE_SANDBOX", raising=False)
    seen = {}

    def fake_run(cmd, *, capture_output, text, timeout):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "hello\n", "")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = run_command(command='echo "hello world"', timeout=10)
    assert "hello\n" in result
    assert "exit code: 0" in result
    assert seen["cmd"] == ["echo", "hello world"]


def test_run_command_host_timeout(monkeypatch):
    """Host execution handles subprocess timeout."""
    monkeypatch.delenv("MAGECODE_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr("subprocess.run", fake_run)
    result = run_command(command="sleep 10", timeout=1)
    assert "timed out" in result
    assert "exit code: 124" in result


def test_run_command_host_command_not_found(monkeypatch):
    """Host execution reports missing commands clearly."""
    monkeypatch.delenv("MAGECODE_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        raise FileNotFoundError("no such file")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = run_command(command="no_such_cmd", timeout=10)
    assert "command not found" in result.lower()


def test_run_command_sandbox_opt_in_env(monkeypatch):
    """MAGECODE_SANDBOX=1 routes to the Docker sandbox."""
    from magecode.sandbox import SandboxResult

    def fake_sandbox(command, *, timeout=30, **kwargs):
        return SandboxResult(
            stdout="sandboxed\n", stderr="", exit_code=0, timed_out=False
        )

    monkeypatch.setenv("MAGECODE_SANDBOX", "1")
    monkeypatch.setattr("magecode.sandbox.run_in_sandbox", fake_sandbox)
    result = run_command(command="echo hi", timeout=10)
    assert "sandboxed" in result
    assert "exit code: 0" in result


def test_run_command_sandbox_opt_in_flag(monkeypatch):
    """--sandbox flag sets MAGECODE_SANDBOX=1 in the environment."""
    from magecode.cli import main

    monkeypatch.delenv("MAGECODE_SANDBOX", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")

    def fake_core_loop(**kwargs):
        assert os.environ.get("MAGECODE_SANDBOX") == "1"
        return None

    with patch("magecode.cli.run_core_loop", side_effect=fake_core_loop):
        code = main(["-p", "run something", "--sandbox"])
    assert code == 0


def test_run_command_host_timeout_with_output(monkeypatch):
    """Host timeout includes stdout/stderr when present."""
    monkeypatch.delenv("MAGECODE_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(
            cmd, 1, output=b"partial out", stderr="partial err"
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    result = run_command(command="sleep 10", timeout=1)
    assert "partial out" in result
    assert "partial err" in result
    assert "exit code: 124" in result
    assert "timed out" in result


def test_run_command_host_stdout_path():
    """_run_host includes stdout in output when present."""
    from magecode.tools.run_command import _run_host

    class FakeCompleted:
        stdout = "hello\n"
        stderr = ""
        returncode = 0

    import subprocess

    orig_run = subprocess.run
    try:
        subprocess.run = lambda *a, **k: FakeCompleted()
        result = _run_host("echo hi", 10)
    finally:
        subprocess.run = orig_run
    assert "stdout:\nhello\n" in result
    assert "exit code: 0" in result


def test_run_command_host_empty_stdout():
    """_run_host handles empty stdout (falsey branch)."""
    from magecode.tools.run_command import _run_host

    class FakeCompleted:
        stdout = ""
        stderr = "some error\n"
        returncode = 1

    import subprocess

    orig_run = subprocess.run
    try:
        subprocess.run = lambda *a, **k: FakeCompleted()
        result = _run_host("false", 10)
    finally:
        subprocess.run = orig_run
    assert "stderr:\nsome error\n" in result
    assert "exit code: 1" in result
    assert "stdout:" not in result


def test_run_command_sandbox_with_stderr_and_timeout(monkeypatch):
    """Sandbox mode passes through stderr and timed_out flag."""
    from magecode.sandbox import SandboxResult

    def fake_sandbox(command, *, timeout=30, **kwargs):
        return SandboxResult(
            stdout="", stderr="sandbox err", exit_code=1, timed_out=True
        )

    monkeypatch.setenv("MAGECODE_SANDBOX", "1")
    monkeypatch.setattr("magecode.sandbox.run_in_sandbox", fake_sandbox)
    result = run_command(command="bad cmd", timeout=10)
    assert "sandbox err" in result
    assert "exit code: 1" in result
    assert "timed out" in result


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

    mock_urlopen = "magecode.tools.web_search.urllib.request.urlopen"
    with patch(mock_urlopen, return_value=FakeResponse()):
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

    mock_urlopen = "magecode.tools.web_search.urllib.request.urlopen"
    with patch(mock_urlopen, return_value=FakeResponse()):
        result = web_search(query="test")
    assert "Result One: https://example.com/one" in result
    assert "Result Two: https://example.com/two" in result


def test_web_search_network_error(monkeypatch):
    with patch(
        "magecode.tools.web_search.urllib.request.urlopen",
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

    mock_urlopen = "magecode.tools.web_search.urllib.request.urlopen"
    with patch(mock_urlopen, return_value=FakeResponse()):
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

    mock_urlopen = "magecode.tools.web_search.urllib.request.urlopen"
    with patch(mock_urlopen, return_value=FakeResponse()):
        result = web_search(query="test")
    assert "Real Result: https://example.com/two" in result
    assert "https://example.com/one" not in result


def test_code_metrics(tmp_path):
    a_py = (
        "def foo():\n"
        "    if x:\n"
        "        pass\n"
        "    return 1\n"
        "\n"
        "class Bar:\n"
        "    def method(self):\n"
        "        pass\n"
    )
    b_py = "# comment\n\ntry:\n    pass\nexcept Exception:\n    pass\n"
    (tmp_path / "a.py").write_text(a_py)
    (tmp_path / "b.py").write_text(b_py)
    result = code_metrics(path=str(tmp_path))
    assert "file_count: 2" in result
    assert "function_count: 1" in result  # only foo() at module level
    assert "class_count: 1" in result
    assert "total_lines:" in result
    assert "estimated_complexity:" in result


def test_code_metrics_binary_file(tmp_path):
    (tmp_path / "binary.py").write_bytes(b"\x00\x01\x02\xff\xfe")
    result = code_metrics(path=str(tmp_path))
    assert "file_count: 1" in result
    assert "total_lines: 0" in result


def test_code_metrics_empty_dir(tmp_path):
    result = code_metrics(path=str(tmp_path))
    assert "file_count: 0" in result
    assert "total_lines: 0" in result


def test_find_duplicates(tmp_path):
    (tmp_path / "a.py").write_text("shared = 1\nshared = 2\nx = 3\n")
    (tmp_path / "b.py").write_text("shared = 1\nshared = 2\ny = 4\n")
    result = find_duplicates(path=str(tmp_path), min_lines=2)
    assert "Duplicate block" in result


def test_find_duplicates_empty_path(tmp_path):
    (tmp_path / "a.py").write_text("shared = 1\nshared = 2\nx = 3\n")
    result = find_duplicates(path="", min_lines=2)
    assert "Duplicate block" in result


def test_find_duplicates_binary_file(tmp_path):
    (tmp_path / "binary.py").write_bytes(b"\x00\x01\x02\xff\xfe")
    result = find_duplicates(path=str(tmp_path), min_lines=2)
    assert result == "No duplicate code blocks found."


def test_find_duplicates_no_duplicates(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\ny = 2\nz = 3\n")
    result = find_duplicates(path=str(tmp_path), min_lines=2)
    assert result == "No duplicate code blocks found."


def test_find_duplicates_empty_dir(tmp_path):
    result = find_duplicates(path=str(tmp_path))
    assert result == "No duplicate code blocks found."


def test_generate_docs(tmp_path):
    (tmp_path / "mymod.py").write_text(
        '"""Module docstring."""\n\n\n'
        'def hello():\n    """Say hello."""\n    pass\n\n\n'
        "def no_doc():\n    pass\n\n\n"
        'class Person:\n    """A person."""\n'
        '    def greet(self):\n        """Greet someone."""\n        pass\n\n'
        "    def silent(self):\n        pass\n\n\n"
        "class SilentClass:\n    pass\n"
    )
    result = generate_docs(path=str(tmp_path))
    assert "# Auto-generated Documentation" in result
    assert "## mymod.py" in result
    assert "### Person" in result
    assert "### SilentClass" in result
    assert "- **hello(...)**" in result
    assert "*Say hello.*" in result
    assert "*A person.*" in result
    assert "*Greet someone.*" in result
    assert "- **no_doc(...)**" in result
    assert "  _No docstring_" in result
    assert "- **silent(...)**" in result


def test_generate_docs_syntax_error(tmp_path):
    (tmp_path / "broken.py").write_text("def ::\n  not valid python")
    result = generate_docs(path=str(tmp_path))
    assert "# Auto-generated Documentation" in result


def test_generate_docs_empty_dir(tmp_path):
    result = generate_docs(path=str(tmp_path))
    assert "# Auto-generated Documentation" in result


def test_reload_module(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")
    result = execute_tool(
        "reload_module",
        json.dumps({"module_name": "test_module", "file_path": str(target)}),
        read_files={str(target)},
    )
    assert "Reloaded module" in result
    assert str(target) in result


def test_reload_module_no_py_extension(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")
    no_ext = str(tmp_path / "mymodule")
    result = execute_tool(
        "reload_module",
        json.dumps({"module_name": "test_module", "file_path": no_ext}),
        read_files={no_ext},
    )
    assert "Reloaded module" in result


def test_reload_module_invalid_path(tmp_path):
    # Directory with .py extension - spec_from_file_location returns None spec
    os.mkdir(tmp_path / "notamodule.py")
    result = execute_tool(
        "reload_module",
        json.dumps(
            {"module_name": "bad_module", "file_path": str(tmp_path / "notamodule.py")}
        ),
        read_files={str(tmp_path / "notamodule.py")},
    )
    assert result.startswith("Error:")


def test_reload_module_self(tmp_path):
    import shutil

    target = tmp_path / "read_file_copy.py"
    shutil.copy("src/magecode/tools/read_file.py", target)
    reload_args = {
        "module_name": "magecode.tools.read_file",
        "file_path": str(target),
    }
    result = execute_tool(
        "reload_module",
        json.dumps(reload_args),
        read_files={str(target)},
    )
    assert "Reloaded module" in result


def test_reload_module_spec_none(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")

    with patch("importlib.util.spec_from_file_location", return_value=None):
        result = execute_tool(
            "reload_module",
            json.dumps({"module_name": "test_module", "file_path": str(target)}),
            read_files={str(target)},
        )
    assert result.startswith("Error:")


def test_reload_module_not_read(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")
    result = execute_tool(
        "reload_module",
        json.dumps({"module_name": "test_module", "file_path": str(target)}),
        read_files=set(),
    )
    assert result.startswith("Refused:")


def test_get_module_mtime():
    assert get_module_mtime("never_loaded") is None


def test_reload_module_no_read_files_tracker(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")
    result = execute_tool(
        "reload_module",
        json.dumps({"module_name": "test_module", "file_path": str(target)}),
        read_files=None,
    )
    assert result.startswith("Refused:")


def test_reload_module_no_changes(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")
    read_files = {str(target)}
    result1 = execute_tool(
        "reload_module",
        json.dumps({"module_name": "test_module", "file_path": str(target)}),
        read_files=read_files,
    )
    assert "Reloaded module" in result1
    result2 = execute_tool(
        "reload_module",
        json.dumps({"module_name": "test_module", "file_path": str(target)}),
        read_files=read_files,
    )
    assert "No changes detected" in result2


def test_reload_module_getmtime_oserror(tmp_path):
    """getmtime OSError is defensive: reload still proceeds."""
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")
    read_files = {str(target)}
    result1 = execute_tool(
        "reload_module",
        json.dumps({"module_name": "test_module_oserr", "file_path": str(target)}),
        read_files=read_files,
    )
    assert "Reloaded module" in result1
    calls = {"n": 0}

    def flaky_getmtime(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("no access")
        return 1234567890.0

    with patch("os.path.getmtime", side_effect=flaky_getmtime):
        result2 = execute_tool(
            "reload_module",
            json.dumps({"module_name": "test_module_oserr", "file_path": str(target)}),
            read_files=read_files,
        )
    assert "Reloaded module" in result2


def test_tool_decorator_registers_schema_and_execution():
    """A new tool decorated with @tool is auto-registered in both registries."""

    @tool(
        name="my_test_tool",
        description="""My test tool.\nManual:\n  - Provide a name.\n""",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "A name.",
                }
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    )
    def my_test_tool(*, name: str) -> str:
        return f"Hello, {name}!"

    # Registered for execution
    assert "my_test_tool" in _TOOLS
    assert _TOOLS["my_test_tool"] is my_test_tool
    assert my_test_tool(name="world") == "Hello, world!"

    # Registered in schemas
    schemas = tool_schemas()
    schema_names = {s["function"]["name"] for s in schemas}
    assert "my_test_tool" in schema_names

    my_schema = next(s for s in schemas if s["function"]["name"] == "my_test_tool")
    assert my_schema["function"]["description"].startswith("My test tool.")
    assert my_schema["function"]["parameters"]["required"] == ["name"]

    # Execute through execute_tool
    result = execute_tool(
        "my_test_tool",
        json.dumps({"name": "Alice"}),
    )
    assert result == "Hello, Alice!"


def test_tool_infer_from_function():
    """Test that @tool infers name, description, and params from the function."""

    @tool
    def greet(*, name: str, greeting: str = "Hello") -> str:
        """Greet someone by name.

        Args:
            name: The person's name.
            greeting: The greeting to use.
        """
        return f"{greeting}, {name}!"

    schemas = tool_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "greet")
    assert schema["function"]["description"] == "Greet someone by name."
    props = schema["function"]["parameters"]["properties"]
    assert props["name"]["type"] == "string"
    assert props["name"]["description"] == "The person's name."
    assert props["greeting"]["type"] == "string"
    assert props["greeting"]["description"] == "The greeting to use."
    required = schema["function"]["parameters"]["required"]
    assert "name" in required
    assert "greeting" not in required  # has default, so not required


def test_tool_unannotated_parameter():
    """Test that unannotated parameters default to string type."""

    @tool
    def my_tool(*, name) -> str:
        """A tool with unannotated parameter.

        Args:
            name: Just a name.
        """
        return name

    schemas = tool_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "my_tool")
    props = schema["function"]["parameters"]["properties"]
    assert props["name"]["type"] == "string"


def test_tool_optional_parameter():
    """Test that Optional[str] parameters unwrapped to string."""

    from typing import Optional

    @tool
    def my_tool(*, name: Optional[str] = None) -> str:
        """A tool with Optional parameter.

        Args:
            name: Optional name.
        """
        return name or ""

    schemas = tool_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "my_tool")
    props = schema["function"]["parameters"]["properties"]
    assert props["name"]["type"] == "string"


def test_tool_override_description():
    """Test that description= overrides docstring."""

    @tool(description="Custom description.")
    def my_tool(*, name: str) -> str:
        """Original docstring description.

        Args:
            name: A name.
        """
        return name

    schemas = tool_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "my_tool")
    assert schema["function"]["description"] == "Custom description."


def test_tool_override_parameters():
    """Test that parameters= overrides signature inference."""

    @tool(
        parameters={
            "type": "object",
            "properties": {
                "custom": {"type": "string", "description": "A custom param."}
            },
            "required": ["custom"],
            "additionalProperties": False,
        }
    )
    def my_tool(*, name: str) -> str:
        """Original description.

        Args:
            name: Original param.
        """
        return name

    schemas = tool_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "my_tool")
    props = schema["function"]["parameters"]["properties"]
    assert "custom" in props
    assert "name" not in props
    required = schema["function"]["parameters"]["required"]
    assert required == ["custom"]


def test_tool_self_parameter_skipped():
    """Test that self/cls parameters are skipped."""

    class MyClass:
        @tool
        def my_method(self, *, name: str) -> str:
            """A method with self.

            Args:
                name: A name.
            """
            return name

    schemas = tool_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "my_method")
    props = schema["function"]["parameters"]["properties"]
    assert "self" not in props
    assert "name" in props


def test_tool_type_none_parameter():
    """Test that Union[type(None)] annotation falls back to string type."""
    from typing import Union

    @tool
    def my_tool(*, name: Union[type(None)] = None) -> str:
        """A tool with Union[type(None)] parameter.

        Args:
            name: Optional none param.
        """
        return name or ""

    schemas = tool_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "my_tool")
    props = schema["function"]["parameters"]["properties"]
    assert props["name"]["type"] == "string"


def test_tool_optional_none_parameter():
    """Test that Optional[None] annotation falls back to string type."""
    from typing import Optional

    @tool
    def my_tool(*, name: Optional[None] = None) -> str:
        """A tool with Optional[None] parameter.

        Args:
            name: Optional none param.
        """
        return name or ""

    schemas = tool_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "my_tool")
    props = schema["function"]["parameters"]["properties"]
    assert props["name"]["type"] == "string"


def test_tool_union_str_int_parameter():
    """Test that Union[str, int] recursively resolves to string type."""
    from typing import Union

    @tool
    def my_tool(*, name: Union[str, int] = "default") -> str:
        """A tool with Union[str, int] parameter.

        Args:
            name: A string or int param.
        """
        return str(name)

    schemas = tool_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "my_tool")
    props = schema["function"]["parameters"]["properties"]
    assert props["name"]["type"] == "string"
    assert props["name"]["description"] == "A string or int param."


def test_python_type_to_json_schema_type_all_none_args():
    """Test that Union with all-None args falls back to string type."""

    class MockAnnotation:
        __origin__ = type(None)
        __args__ = (type(None),)

    result = _python_type_to_json_schema_type(MockAnnotation())
    assert result == "string"


def test_python_type_to_json_schema_type_union_str_int():
    """Test that Union[str, int] recursively resolves to string type via line 29."""

    class MockAnnotation:
        __origin__ = type(None)  # not used, but set for completeness
        __args__ = (str, int)

    result = _python_type_to_json_schema_type(MockAnnotation())
    assert result == "string"


def test_parse_docstring_args_line_without_colon():
    """Test docstring parsing when Args section has a line without a colon."""
    from magecode.tools import _parse_docstring

    desc, param_descs = _parse_docstring(
        """Do something.

        Args:
            name: The person's name.
            this line has no colon
            age: The person's age.
        """
    )
    assert desc == "Do something."
    assert param_descs == {"name": "The person's name.", "age": "The person's age."}


def test_python_type_to_json_schema_type_empty_args():
    """Test that Union with empty args falls back to string type."""

    class MockAnnotation:
        __origin__ = object
        __args__ = ()

    result = _python_type_to_json_schema_type(MockAnnotation())
    assert result == "string"


def test_grep_files_with_file_path(tmp_path):
    """grep_files should search a single file when path points to a file."""
    target = tmp_path / "test.txt"
    target.write_text("hello world\ntest line\ndef foo():\n    pass\n")
    result = grep_files(pattern=r"def ", path=str(target))
    assert "test.txt:3: def foo():" in result


def test_web_search_bot_detection():
    """web_search should return a clear error when DuckDuckGo blocks requests."""
    html = """<html><title>DuckDuckGo</title>
    <body>
    <p>Unusual traffic from your computer network.</p>
    <p>This page checks to see if it's really you sending the requests.</p>
    </body></html>"""

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return html.encode("utf-8")

    mock_urlopen = "magecode.tools.web_search.urllib.request.urlopen"
    with patch(mock_urlopen, return_value=FakeResponse()):
        result = web_search(query="anything")
    assert "bot detection" in result.lower()


def test_turn_limit_reached():
    """run_core_loop should raise TurnLimitReached when max_turns exceeded."""
    from types import SimpleNamespace

    from magecode.core_loop import TurnLimitReached, run_core_loop

    def create(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        role="assistant",
                        content="I'll keep going",
                        tool_calls=[
                            SimpleNamespace(
                                id="call-1",
                                type="function",
                                function=SimpleNamespace(
                                    name="read_file", arguments='{"path": "x.txt"}'
                                ),
                            )
                        ],
                    )
                )
            ],
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    messages = [{"role": "user", "content": "keep going forever"}]
    try:
        run_core_loop(
            model="test/model",
            messages=messages,
            client=client,
            max_turns=2,
            reply_prefix="< ",
        )
        assert False, "Expected TurnLimitReached"
    except TurnLimitReached as e:
        assert "Turn limit" in str(e)
