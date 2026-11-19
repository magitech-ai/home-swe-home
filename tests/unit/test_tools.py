"""Tests for home_swe_home.tools (anima Service components)."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from anima import Context, Service

from home_swe_home.sandbox import SandboxService
from home_swe_home.tools import (
    TOOL_SERVICES,
    ReadFileService,
    ToolService,
    WriteFileService,
)


def _build_context() -> Context:
    ctx = Context()
    for service_cls in (*TOOL_SERVICES, ToolService, SandboxService):
        ctx.use(service_cls)
    return ctx


def execute_tool(ctx, function_name, arguments_json, *, read_files=None):
    """Test shim: call the ToolService capability on the Context."""
    return ctx.tools.execute(function_name, arguments_json, read_files=read_files)


def _tool(ctx: Context, name: str):
    service = ctx.reflect.get(name)
    assert service is not None, f"Service {name} not mounted"
    return service


def test_tool_services_have_descriptions():
    services = [_tool(_build_context(), name) for name in ["read_file", "write_file"]]
    for service in services:
        assert service.__doc__, f"Service {service.name} has no docstring"


def test_tool_service_name_from_class():
    """Service name is derived from class name stripping 'Service' suffix."""
    from anima import Context

    ctx = Context()
    ctx.use(ReadFileService)
    ctx.use(WriteFileService)
    assert ctx.read_file.name == "read_file"
    assert ctx.write_file.name == "write_file"


def test_write_then_read_file(tmp_path):
    target = tmp_path / "note.txt"
    ctx = _build_context()
    assert (
        _tool(ctx, "write_file")(path=str(target), content="hello world")
        == f"Wrote 11 characters to {target}."
    )
    assert _tool(ctx, "read_file")(path=str(target)) == "hello world"


def test_read_file_missing(tmp_path):
    result = execute_tool(
        _build_context(),
        "read_file",
        json.dumps({"path": str(tmp_path / "does-not-exist.txt")}),
    )
    assert result.startswith("Error: FileNotFoundError: ")


def test_list_directory(tmp_path):
    (tmp_path / "a.txt").write_text("")
    (tmp_path / "sub").mkdir()
    result = _tool(_build_context(), "list_directory")(path=str(tmp_path))
    assert "a.txt" in result
    assert "sub/" in result


def test_list_directory_empty(tmp_path):
    assert _tool(_build_context(), "list_directory")(path=str(tmp_path)) == "(empty)"


def test_grep_files(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "one.txt").write_text("alpha beta\ngamma alpha\n")
    (tmp_path / "two.txt").write_text("no match here\n")
    result = _tool(_build_context(), "grep_files")(pattern=r"alpha", path=str(tmp_path))
    assert "one.txt:1: alpha beta" in result
    assert "one.txt:2: gamma alpha" in result


def test_grep_files_no_matches(tmp_path):
    (tmp_path / "one.txt").write_text("nothing\n")
    assert (
        _tool(_build_context(), "grep_files")(pattern=r"zzz", path=str(tmp_path))
        == "No matches."
    )


def test_grep_files_skips_binary(tmp_path):
    text_file = tmp_path / "text.txt"
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01\x02\xff" * 100)
    text_file.write_text("visible line\n")
    expected = f"{text_file}:1: visible line"
    assert (
        _tool(_build_context(), "grep_files")(pattern=r"visible", path=str(tmp_path))
        == expected
    )


def test_grep_files_caps_at_fifty_matches(tmp_path):
    content = "\n".join(f"match {i}" for i in range(60)) + "\n"
    (tmp_path / "many.txt").write_text(content)
    lines = _tool(_build_context(), "grep_files")(
        pattern=r"match", path=str(tmp_path)
    ).splitlines()
    assert len(lines) == 50


def test_run_command_success(monkeypatch):
    from home_swe_home.sandbox import SandboxResult

    def fake_sandbox(command, *, timeout=30, **kwargs):
        return SandboxResult(
            stdout="out\n", stderr="err\n", exit_code=3, timed_out=False
        )

    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "1")
    monkeypatch.setattr(
        SandboxService, "run", lambda self, command, **kw: fake_sandbox(command, **kw)
    )
    result = _tool(_build_context(), "run_command")(
        command="sh -c 'echo out; echo err >&2; exit 3'", timeout=10
    )
    assert "stdout:\nout\n" in result
    assert "stderr:\nerr\n" in result
    assert "exit code: 3" in result


def test_run_command_no_output(monkeypatch):
    from home_swe_home.sandbox import SandboxResult

    def fake_sandbox(command, *, timeout=30, **kwargs):
        return SandboxResult(stdout="", stderr="", exit_code=0, timed_out=False)

    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "1")
    monkeypatch.setattr(
        SandboxService, "run", lambda self, command, **kw: fake_sandbox(command, **kw)
    )
    assert (
        _tool(_build_context(), "run_command")(command="true", timeout=10)
        == "exit code: 0"
    )


def test_run_command_host_default(monkeypatch):
    """run_command runs on the host by default (no sandbox)."""
    monkeypatch.delenv("HOME_SWE_HOME_SANDBOX", raising=False)

    def fake_run(cmd, *, capture_output, text, timeout):
        return SimpleNamespace(returncode=0, stdout="out\n", stderr="err\n")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = _tool(_build_context(), "run_command")(
        command="echo out; echo err >&2", timeout=10
    )
    assert "stdout:\nout\n" in result
    assert "stderr:\nerr\n" in result
    assert "exit code: 0" in result


def test_execute_tool_unknown_tool():
    ctx = _build_context()
    result = execute_tool(ctx, "no_such_tool", "{}")
    assert result.startswith("Error: unknown tool 'no_such_tool'. Use one of: ")
    for name in {"read_file", "write_file", "edit_file", "delete_file"}:
        assert name in result


def test_execute_tool_bad_arguments():
    ctx = _build_context()
    result = execute_tool(ctx, "read_file", "{not json")
    assert result.startswith("Error: invalid tool arguments: ")


def test_edit_file_replaces_exact_text(tmp_path):
    target = tmp_path / "script.txt"
    target.write_text("print('hello')\n")
    read_files = {str(target)}
    result = execute_tool(
        _build_context(),
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
        _build_context(),
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
        _build_context(),
        "edit_file",
        json.dumps({"path": str(target), "old_string": "hello", "new_string": "world"}),
        read_files=set(),
    )
    assert result.startswith(f"Refused: '{target}' has not been read yet.")
    assert "Call read_file" in result
    assert target.read_text() == "print('hello')\n"


def test_edit_file_old_string_not_found(tmp_path):
    target = tmp_path / "script.txt"
    target.write_text("print('hello')\n")
    read_files = {str(target)}
    result = execute_tool(
        _build_context(),
        "edit_file",
        json.dumps(
            {"path": str(target), "old_string": "goodbye", "new_string": "world"}
        ),
        read_files=read_files,
    )
    assert result.startswith(f"Error: old_string not found in {target}.")
    assert "read_file" in result
    assert target.read_text() == "print('hello')\n"


def test_delete_file(tmp_path):
    target = tmp_path / "temp.txt"
    target.write_text("temporary\n")
    result = _tool(_build_context(), "delete_file")(path=str(target))
    assert result == f"Deleted {target}."
    assert not target.exists()


def test_delete_file_nonexistent(tmp_path):
    target = tmp_path / "missing.txt"
    result = _tool(_build_context(), "delete_file")(path=str(target))
    assert result.startswith("Error: FileNotFoundError: ")


def test_web_search_no_network(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"<html></html>"

    mock_urlopen = "home_swe_home.tools.web_search.urllib.request.urlopen"
    with patch(mock_urlopen, return_value=FakeResponse()):
        result = _tool(_build_context(), "web_search")(query="anything")
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

    mock_urlopen = "home_swe_home.tools.web_search.urllib.request.urlopen"
    with patch(mock_urlopen, return_value=FakeResponse()):
        result = _tool(_build_context(), "web_search")(query="test")
    assert "Result One: https://example.com/one" in result
    assert "Result Two: https://example.com/two" in result


def test_web_search_network_error(monkeypatch):
    with patch(
        "home_swe_home.tools.web_search.urllib.request.urlopen",
        side_effect=OSError("network down"),
    ):
        result = _tool(_build_context(), "web_search")(query="test")
    assert result.startswith("Error: web search failed: network down.")
    assert "retry the query" in result


def test_execute_tool_read_file_tracks_read_files(tmp_path):
    target = tmp_path / "track.txt"
    target.write_text("contents\n")
    read_files: set[str] = set()
    result = execute_tool(
        _build_context(),
        "read_file",
        json.dumps({"path": str(target)}),
        read_files=read_files,
    )
    assert result == "contents\n"
    assert read_files == {str(target)}


def test_execute_tool_write_file_tracks_read_files(tmp_path):
    target = tmp_path / "track2.txt"
    read_files: set[str] = set()
    result = execute_tool(
        _build_context(),
        "write_file",
        json.dumps({"path": str(target), "content": "data"}),
        read_files=read_files,
    )
    assert result == f"Wrote 4 characters to {target}."
    assert read_files == {str(target)}
    assert target.read_text() == "data"


def test_web_search_many_results_triggers_break(monkeypatch):
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

    mock_urlopen = "home_swe_home.tools.web_search.urllib.request.urlopen"
    with patch(mock_urlopen, return_value=FakeResponse()):
        result = _tool(_build_context(), "web_search")(query="test")
    lines = result.splitlines()
    assert len(lines) == 8  # capped at 8


def test_web_search_skips_empty_title(monkeypatch):
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

    mock_urlopen = "home_swe_home.tools.web_search.urllib.request.urlopen"
    with patch(mock_urlopen, return_value=FakeResponse()):
        result = _tool(_build_context(), "web_search")(query="test")
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
    result = _tool(_build_context(), "code_metrics")(path=str(tmp_path))
    assert "file_count: 2" in result
    assert "function_count: 1" in result
    assert "class_count: 1" in result
    assert "total_lines:" in result
    assert "estimated_complexity:" in result


def test_code_metrics_binary_file(tmp_path):
    (tmp_path / "binary.py").write_bytes(b"\x00\x01\x02\xff\xfe")
    result = _tool(_build_context(), "code_metrics")(path=str(tmp_path))
    assert "file_count: 1" in result
    assert "total_lines: 0" in result


def test_code_metrics_empty_dir(tmp_path):
    result = _tool(_build_context(), "code_metrics")(path=str(tmp_path))
    assert "file_count: 0" in result
    assert "total_lines: 0" in result


def test_find_duplicates(tmp_path):
    (tmp_path / "a.py").write_text("shared = 1\nshared = 2\nx = 3\n")
    (tmp_path / "b.py").write_text("shared = 1\nshared = 2\ny = 4\n")
    result = _tool(_build_context(), "find_duplicates")(path=str(tmp_path), min_lines=2)
    assert "Duplicate block" in result


def test_find_duplicates_empty_path(tmp_path):
    (tmp_path / "a.py").write_text("shared = 1\nshared = 2\nx = 3\n")
    result = _tool(_build_context(), "find_duplicates")(path="", min_lines=2)
    assert "Duplicate block" in result


def test_find_duplicates_binary_file(tmp_path):
    (tmp_path / "binary.py").write_bytes(b"\x00\x01\x02\xff\xfe")
    result = _tool(_build_context(), "find_duplicates")(path=str(tmp_path), min_lines=2)
    assert result == "No duplicate code blocks found."


def test_find_duplicates_no_duplicates(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\ny = 2\nz = 3\n")
    result = _tool(_build_context(), "find_duplicates")(path=str(tmp_path), min_lines=2)
    assert result == "No duplicate code blocks found."


def test_find_duplicates_empty_dir(tmp_path):
    result = _tool(_build_context(), "find_duplicates")(path=str(tmp_path))
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
    result = _tool(_build_context(), "generate_docs")(path=str(tmp_path))
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
    result = _tool(_build_context(), "generate_docs")(path=str(tmp_path))
    assert "# Auto-generated Documentation" in result


def test_generate_docs_empty_dir(tmp_path):
    result = _tool(_build_context(), "generate_docs")(path=str(tmp_path))
    assert "# Auto-generated Documentation" in result


def test_reload_module(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")
    result = execute_tool(
        _build_context(),
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
        _build_context(),
        "reload_module",
        json.dumps({"module_name": "test_module", "file_path": no_ext}),
        read_files={no_ext},
    )
    assert "Reloaded module" in result


def test_reload_module_invalid_path(tmp_path):
    os.mkdir(tmp_path / "notamodule.py")
    result = execute_tool(
        _build_context(),
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
    shutil.copy("src/home_swe_home/tools/read_file.py", target)
    result = execute_tool(
        _build_context(),
        "reload_module",
        json.dumps(
            {"module_name": "home_swe_home.tools.read_file", "file_path": str(target)}
        ),
        read_files={str(target)},
    )
    assert "Reloaded module" in result


def test_reload_module_spec_none(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")

    with patch("importlib.util.spec_from_file_location", return_value=None):
        result = execute_tool(
            _build_context(),
            "reload_module",
            json.dumps({"module_name": "test_module", "file_path": str(target)}),
            read_files={str(target)},
        )
    assert result.startswith("Error:")


def test_reload_module_not_read(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")
    result = execute_tool(
        _build_context(),
        "reload_module",
        json.dumps({"module_name": "test_module", "file_path": str(target)}),
        read_files=set(),
    )
    assert result.startswith("Refused:")


def test_reload_module_no_read_files_tracker(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")
    result = execute_tool(
        _build_context(),
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
        _build_context(),
        "reload_module",
        json.dumps({"module_name": "test_module", "file_path": str(target)}),
        read_files=read_files,
    )
    assert "Reloaded module" in result1
    result2 = execute_tool(
        _build_context(),
        "reload_module",
        json.dumps({"module_name": "test_module", "file_path": str(target)}),
        read_files=read_files,
    )
    assert "No changes detected" in result2


def test_reload_module_stat_oserror(tmp_path):
    """os.stat OSError returns a clear error message."""
    target = tmp_path / "mymodule.py"
    target.write_text("VALUE = 1\n")

    import home_swe_home.tools.reload_module as reload_mod

    orig = reload_mod.os.stat

    def failing_stat(path):
        raise OSError("no access")

    try:
        reload_mod.os.stat = failing_stat
        result = execute_tool(
            _build_context(),
            "reload_module",
            json.dumps({"module_name": "test_stat_err", "file_path": str(target)}),
            read_files={str(target)},
        )
    finally:
        reload_mod.os.stat = orig
    assert result.startswith("Error: could not stat")


def test_reload_module_same_size_same_second_not_stale(tmp_path):
    """Regression: same-size edits in one second must not run stale bytecode."""
    marker = tmp_path / "marker.txt"
    target = tmp_path / "spike_mod.py"
    # Import writes the marker; AAAA/BBBB are same length so the bytecode
    # cache key (mtime seconds, size) is identical across edits.
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('AAAA')\n"
    target.write_text(source)
    module_name = "spike_reload_mod"
    read_files = {str(target)}

    first = execute_tool(
        _build_context(),
        "reload_module",
        json.dumps({"module_name": module_name, "file_path": str(target)}),
        read_files=read_files,
    )
    assert "Reloaded module" in first
    assert marker.read_text() == "AAAA"

    # Same byte length, same second -> without cache invalidation the tool
    # would execute the stale 'AAAA' bytecode instead of 'BBBB'.
    target.write_text(source.replace("AAAA", "BBBB"))
    second = execute_tool(
        _build_context(),
        "reload_module",
        json.dumps({"module_name": module_name, "file_path": str(target)}),
        read_files=read_files,
    )
    assert "Reloaded module" in second
    assert marker.read_text() == "BBBB"  # proves fresh bytecode ran


def test_grep_files_with_file_path(tmp_path):
    target = tmp_path / "test.txt"
    target.write_text("hello world\ntest line\ndef foo():\n    pass\n")
    result = _tool(_build_context(), "grep_files")(pattern=r"def ", path=str(target))
    assert "test.txt:3: def foo():" in result


def test_web_search_bot_detection(monkeypatch):
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

    mock_urlopen = "home_swe_home.tools.web_search.urllib.request.urlopen"
    with patch(mock_urlopen, return_value=FakeResponse()):
        result = _tool(_build_context(), "web_search")(query="anything")
    assert "bot detection" in result.lower()


def test_web_search_decodes_uddg_wrapper(monkeypatch):
    """DDG's uddg= redirect wrapper is decoded to the real target URL."""
    from home_swe_home.tools.web_search import _decode_href

    wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage%3Fa%3D1"
    assert _decode_href(wrapped) == "https://example.com/page?a=1"
    # uddg= not the first query param
    wrapped2 = "//duckduckgo.com/l/?foo=bar&uddg=https%3A%2F%2Fexample.com%2Fx"
    assert _decode_href(wrapped2) == "https://example.com/x"
    # "uddg=" present but not a query param -> falls through to normalize
    assert _decode_href("https://example.com/path?uddgx=1") == (
        "https://example.com/path?uddgx=1"
    )
    # "uddg=" with no '?' at all -> falls through
    assert _decode_href("https://example.com/uddg=thing") == (
        "https://example.com/uddg=thing"
    )


def test_web_search_protocol_relative_href(monkeypatch):
    """Protocol-relative result links are normalized to https."""
    from home_swe_home.tools.web_search import _decode_href

    assert _decode_href("//example.com/path") == "https://example.com/path"


def test_web_search_lite_fallback(monkeypatch):
    """When the HTML endpoint is bot-blocked, the Lite endpoint is tried."""
    calls = []

    class ChallengeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"<html><p>unusual traffic detected</p></html>"

    lite_html = (
        "<html><body>"
        '<a class="result-link" href="https://lite.example.com/one">Lite One</a>'
        "</body></html>"
    )

    class LiteResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return lite_html.encode()

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if "html.duckduckgo.com" in req.full_url:
            return ChallengeResponse()
        return LiteResponse()

    with patch(
        "home_swe_home.tools.web_search.urllib.request.urlopen", new=fake_urlopen
    ):
        result = _tool(_build_context(), "web_search")(query="test")
    assert "Lite One: https://lite.example.com/one" in result
    assert len(calls) == 2  # both endpoints tried


def test_web_search_bot_signal_anomaly(monkeypatch):
    """The 'anomaly' bot signal is detected."""
    from home_swe_home.tools.web_search import _is_bot_challenge

    assert _is_bot_challenge("<html><p>Anomaly detected</p></html>") is True
    assert _is_bot_challenge("<html><body>nothing special</body></html>") is False


def test_web_search_searxng_first(monkeypatch):
    """SEARXNG_URL routes to the instance's JSON API and returns real URLs."""
    import json

    from home_swe_home.tools.web_search import _search_searxng

    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        assert "format=json" in req.full_url
        assert "mysearch.local/search" in req.full_url

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(
                    {
                        "results": [
                            {
                                "title": "SearXNG Result",
                                "url": "https://example.com/searx",
                                "content": "snippet",
                                "engine": "google",
                            }
                        ]
                    }
                ).encode()

        return Response()

    monkeypatch.setattr(
        "home_swe_home.tools.web_search.urllib.request.urlopen", fake_urlopen
    )
    results = _search_searxng("https://mysearch.local", "test query")
    assert results == ["SearXNG Result: https://example.com/searx"]
    assert len(calls) == 1


def test_web_search_searxng_service_uses_json(monkeypatch):
    """With SEARXNG_URL set, the service calls SearXNG and skips DDG."""
    import json

    monkeypatch.setenv("SEARXNG_URL", "https://mysearch.local")

    def fake_urlopen(req, timeout):
        assert "mysearch.local/search" in req.full_url

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(
                    {"results": [{"title": "Found", "url": "https://found.example/a"}]}
                ).encode()

        return Response()

    monkeypatch.setattr(
        "home_swe_home.tools.web_search.urllib.request.urlopen", fake_urlopen
    )
    result = _tool(_build_context(), "web_search")(query="test")
    assert result == "Found: https://found.example/a"


def test_web_search_searxng_falls_back_on_403(monkeypatch):
    """A SearXNG 403 (json format disabled) falls back to DuckDuckGo."""
    from urllib.error import HTTPError

    monkeypatch.setenv("SEARXNG_URL", "https://mysearch.local")

    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if "mysearch.local" in req.full_url:
            raise HTTPError(req.full_url, 403, "forbidden", {}, None)

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return (
                    b'<html><a rel="nofollow" class="result__a" '
                    b'href="https://ddg.example/x">DDG Result</a></html>'
                )

        return Response()

    monkeypatch.setattr(
        "home_swe_home.tools.web_search.urllib.request.urlopen", fake_urlopen
    )
    result = _tool(_build_context(), "web_search")(query="test")
    assert "DDG Result: https://ddg.example/x" in result
    assert any("duckduckgo.com" in url for url in calls)  # DDG was actually called


def test_web_search_searxng_bad_json_falls_back(monkeypatch):
    """Malformed SearXNG JSON returns None so the caller falls back."""
    from home_swe_home.tools.web_search import _search_searxng

    def fake_urlopen(req, timeout):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"not json"

        return Response()

    monkeypatch.setattr(
        "home_swe_home.tools.web_search.urllib.request.urlopen", fake_urlopen
    )
    assert _search_searxng("https://mysearch.local", "q") is None


def test_web_search_searxng_env_strip(monkeypatch):
    """SEARXNG_URL is stripped of surrounding whitespace and trailing slash."""
    from home_swe_home.tools.web_search import _searxng_url

    monkeypatch.setenv("SEARXNG_URL", "  https://mysearch.local/  ")
    assert _searxng_url() == "https://mysearch.local"
    monkeypatch.delenv("SEARXNG_URL")
    assert _searxng_url() is None


def test_web_search_searxng_skips_empty_and_caps():
    """SearXNG items missing title/url are skipped; results capped at 8."""
    import json

    from home_swe_home.tools.web_search import _search_searxng

    items = [{"title": "", "url": "https://skip.example"}, {"title": "No URL"}] + [
        {"title": f"R{i}", "url": f"https://example.com/{i}"} for i in range(12)
    ]

    def fake_urlopen(req, timeout):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"results": items}).encode()

        return Response()

    with patch(
        "home_swe_home.tools.web_search.urllib.request.urlopen", new=fake_urlopen
    ):
        results = _search_searxng("https://mysearch.local", "q")
    assert results is not None
    assert len(results) == 8  # capped
    assert all("skip.example" not in r for r in results)
    assert results[0] == "R0: https://example.com/0"


@pytest.mark.asyncio
async def test_turn_limit_reached():
    """CoreLoopService should raise TurnLimitReached when max_turns exceeded."""
    from home_swe_home.context import AGENT_SERVICES
    from home_swe_home.core_loop import TurnLimitReached

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
    ctx = Context()
    for cls in AGENT_SERVICES:
        ctx.use(cls)
    await ctx.flush()
    ctx.client._openai = client  # type: ignore[attr-defined]
    messages = [{"role": "user", "content": "keep going forever"}]
    try:
        await ctx.core_loop(
            model="test/model",
            messages=messages,
            max_turns=2,
        )
        assert False, "Expected TurnLimitReached"
    except TurnLimitReached as e:
        assert "Turn limit" in str(e)


@pytest.mark.asyncio
async def test_execute_tool_injects_read_files(monkeypatch):
    """execute_tool injects read_files into tools that accept it."""
    from home_swe_home.tools.run_command import RunCommandService

    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "1")

    ctx = Context()
    ctx.use(RunCommandService)
    ctx.use(ToolService)
    ctx.use(SandboxService)
    await ctx.flush()

    seen = {}

    def fake_sandbox(command, *, timeout=30, **kwargs):
        seen["timeout"] = timeout
        seen["command"] = command
        from home_swe_home.sandbox import SandboxResult

        return SandboxResult(stdout="ok\n", stderr="", exit_code=0, timed_out=False)

    with patch.object(
        SandboxService,
        "run",
        new=lambda self, command, **kw: fake_sandbox(command, **kw),
    ):
        result = execute_tool(
            ctx,
            "run_command",
            '{"command": "echo hi", "timeout": 5}',
            read_files={"/tmp/test"},
        )
    assert "ok" in result


def test_execute_tool_service_raises():
    """execute_tool catches exceptions from service __call__."""
    from anima import Context

    class FailingService(Service):
        name = "failing"

        def __init__(self, ctx):
            super().__init__(ctx, "failing")

        def __call__(self, *, value: str) -> str:
            raise ValueError("boom")

    ctx = Context()
    ctx.use(ToolService)
    ctx.reflect.provide("failing", FailingService(ctx))
    result = execute_tool(ctx, "failing", '{"value": "x"}')
    assert result.startswith("Error: ValueError: boom.")
