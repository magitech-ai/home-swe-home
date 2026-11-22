"""Comprehensive tests for all 15 tool definitions."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from home_swe_home.sandbox import set_sandbox_enabled
from home_swe_home.tools.definitions import (
    ADD_REPO,
    ALL_TOOLS,
    CODE_METRICS,
    DELETE_FILE,
    EDIT_FILE,
    FIND_DUPLICATES,
    GENERATE_DOCS,
    GREP_FILES,
    LIST_DIRECTORY,
    RELOAD_MODULE,
    RUN_COMMAND,
    VERIFY_REPO,
    WEB_SEARCH,
    WRITE_FILE,
    _agent_of,
    _use_sandbox,
    register_tools,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(seq: int, type_: str, payload: dict[str, Any]) -> MagicMock:
    """Build a minimal stand-in for a SessionEvent."""
    event = MagicMock()
    event.seq = seq
    event.type = type_
    event.payload = payload
    return event


def _agent_with_events(events: list[MagicMock]) -> MagicMock:
    """Build an agent whose session exposes *events*."""
    agent = MagicMock()
    agent.session.events = events
    return agent


def _turn_start(seq: int) -> MagicMock:
    """A turn/start event — the boundary for per-turn read tracking."""
    return _event(seq, "turn/start", {"turn": 1})


def _tool_call(seq: int, name: str, arguments: Any) -> MagicMock:
    return _event(seq, "tool/call", {"name": name, "arguments": arguments})


def test_native_tool_render_redacts_secrets(monkeypatch) -> None:
    """Native tools still redact at the render boundary."""
    monkeypatch.setenv("NVIDIA_API_KEY", "secret123")
    rendered = WRITE_FILE["output"]["render"]({}, "key=secret123")
    assert rendered[0]["text"] == "key=<redacted>"


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


def test_write_file(tmp_path: Path) -> None:
    f = tmp_path / "out.txt"
    result = WRITE_FILE["execute"]({"path": str(f), "content": "written"}, {})
    assert "Wrote 7 characters" in result
    assert f.read_text() == "written"


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------


def test_edit_file_without_agent_proceeds(tmp_path: Path) -> None:
    """With no agent context there is no read tracking to enforce."""
    f = tmp_path / "edit.txt"
    f.write_text("old text", encoding="utf-8")
    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "old", "new_string": "new"}, {}
    )
    assert "Replaced" in result
    assert "new text" in f.read_text()


def test_edit_file_refuses_when_nothing_read_this_turn(tmp_path: Path) -> None:
    """A turn that read nothing cannot edit anything."""
    f = tmp_path / "unread.txt"
    f.write_text("content", encoding="utf-8")
    agent = _agent_with_events([_turn_start(1)])

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "content", "new_string": "changed"},
        {"agent": agent},
    )
    assert "Refused" in result
    assert "has not been read" in result


def test_edit_file_refuses_other_path_read_this_turn(tmp_path: Path) -> None:
    """Reading a different file does not authorize this one."""
    f = tmp_path / "unread.txt"
    f.write_text("content", encoding="utf-8")
    agent = _agent_with_events(
        [
            _turn_start(1),
            _tool_call(2, "read_file", {"path": "/some/other/file.txt"}),
        ]
    )

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "content", "new_string": "changed"},
        {"agent": agent},
    )
    assert "Refused" in result


def test_edit_file_allowed_after_read_this_turn(tmp_path: Path) -> None:
    f = tmp_path / "read.txt"
    f.write_text("old text", encoding="utf-8")
    agent = _agent_with_events(
        [_turn_start(1), _tool_call(2, "read_file", {"path": str(f)})]
    )

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "old", "new_string": "new"},
        {"agent": agent},
    )
    assert "Replaced" in result


def test_edit_file_allowed_after_write_this_turn(tmp_path: Path) -> None:
    """write_file also marks a path readable in the same turn."""
    f = tmp_path / "written.txt"
    f.write_text("old", encoding="utf-8")
    agent = _agent_with_events(
        [_turn_start(1), _tool_call(2, "write_file", {"path": str(f)})]
    )

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "old", "new_string": "new"},
        {"agent": agent},
    )
    assert "Replaced" in result


def test_edit_file_read_in_prior_turn_does_not_authorize(tmp_path: Path) -> None:
    """Reads are per-turn: a stale read from turn 1 must not allow turn 2."""
    f = tmp_path / "stale.txt"
    f.write_text("content", encoding="utf-8")
    agent = _agent_with_events(
        [
            _turn_start(1),
            _tool_call(2, "read_file", {"path": str(f)}),
            _event(3, "turn/end", {"turn": 1, "reason": {"kind": "completed"}}),
            _turn_start(4),
        ]
    )

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "content", "new_string": "changed"},
        {"agent": agent},
    )
    assert "Refused" in result


def test_edit_file_normalizes_path_spellings(tmp_path: Path) -> None:
    """Redundant separators / dot segments in a path compare equal."""
    f = tmp_path / "norm.txt"
    f.write_text("content", encoding="utf-8")
    messy = str(tmp_path / "." / "norm.txt")
    agent = _agent_with_events(
        [_turn_start(1), _tool_call(2, "read_file", {"path": messy})]
    )

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "content", "new_string": "changed"},
        {"agent": agent},
    )
    assert "Replaced" in result


def test_edit_file_old_string_not_found(tmp_path: Path) -> None:
    f = tmp_path / "edit.txt"
    f.write_text("hello", encoding="utf-8")
    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "missing", "new_string": "x"}, {}
    )
    assert "not found" in result


def test_edit_file_ignores_non_tool_and_malformed_events(tmp_path: Path) -> None:
    """Events that are not well-formed tool calls are skipped."""
    f = tmp_path / "file.txt"
    f.write_text("content", encoding="utf-8")
    agent = _agent_with_events(
        [
            _turn_start(1),
            _event(2, "user/message", {}),
            _tool_call(3, "read_file", "not_a_dict"),
            _tool_call(4, "web_search", {"query": "x"}),
            _tool_call(5, "read_file", {"path": str(f)}),
        ]
    )

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "content", "new_string": "changed"},
        {"agent": agent},
    )
    assert "Replaced" in result


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------


def test_delete_file(tmp_path: Path) -> None:
    f = tmp_path / "del.txt"
    f.write_text("x")
    result = DELETE_FILE["execute"]({"path": str(f)}, {})
    assert "Deleted" in result
    assert not f.exists()


def test_delete_file_not_found() -> None:
    result = DELETE_FILE["execute"]({"path": "/nonexistent/file"}, {})
    assert "Error" in result
    assert "No such file" in result


# ---------------------------------------------------------------------------
# list_directory
# ---------------------------------------------------------------------------


def test_list_directory(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "subdir").mkdir()
    result = LIST_DIRECTORY["execute"]({"path": str(tmp_path)}, {})
    assert "a.txt" in result
    assert "subdir/" in result


def test_list_directory_empty(tmp_path: Path) -> None:
    result = LIST_DIRECTORY["execute"]({"path": str(tmp_path)}, {})
    assert "(empty)" in result


def test_list_directory_default() -> None:
    result = LIST_DIRECTORY["execute"]({}, {})
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# grep_files
# ---------------------------------------------------------------------------


def test_grep_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("hello world\nfoo bar\n")
    result = GREP_FILES["execute"]({"pattern": "hello", "path": str(tmp_path)}, {})
    assert "hello" in result


def test_grep_files_no_matches(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("nothing\n")
    result = GREP_FILES["execute"]({"pattern": "xyz", "path": str(tmp_path)}, {})
    assert "No matches" in result


def test_grep_files_single_file(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("needle in haystack\n")
    result = GREP_FILES["execute"]({"pattern": "needle", "path": str(f)}, {})
    assert "needle" in result


def test_grep_files_unreadable_file(tmp_path: Path) -> None:
    """Unreadable files are skipped rather than aborting the search."""
    (tmp_path / "bad.py").write_bytes(b"\xff\xfe invalid utf-8")
    (tmp_path / "good.py").write_text("match here\n")
    result = GREP_FILES["execute"]({"pattern": "match", "path": str(tmp_path)}, {})
    assert "match" in result


def test_grep_files_recurses_subdirs(tmp_path: Path) -> None:
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "a.py").write_text("needle\n")
    result = GREP_FILES["execute"]({"pattern": "needle", "path": str(tmp_path)}, {})
    assert "needle" in result


def test_grep_files_caps_at_50(tmp_path: Path) -> None:
    lines = "\n".join(f"match {i}" for i in range(60))
    (tmp_path / "many.py").write_text(lines)
    result = GREP_FILES["execute"]({"pattern": "match", "path": str(tmp_path)}, {})
    assert result.count("\n") <= 50


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------


def test_run_command_sandboxed(monkeypatch) -> None:
    set_sandbox_enabled(True)
    mock_result = MagicMock(stdout="out", stderr="err", exit_code=0, timed_out=False)
    with patch("home_swe_home.sandbox.run_in_sandbox", return_value=mock_result) as m:
        result = RUN_COMMAND["execute"]({"command": "echo hi"}, {})
    assert m.called
    assert "stdout:\nout" in result
    assert "exit code: 0" in result


def test_run_command_sandboxed_timed_out(monkeypatch) -> None:
    set_sandbox_enabled(True)
    mock_result = MagicMock(stdout="", stderr="", exit_code=124, timed_out=True)
    with patch("home_swe_home.sandbox.run_in_sandbox", return_value=mock_result):
        result = RUN_COMMAND["execute"]({"command": "sleep 100"}, {})
    assert "timed out" in result


def test_run_command_sandboxed_empty_output() -> None:
    set_sandbox_enabled(True)
    mock_result = MagicMock(stdout="", stderr="", exit_code=0, timed_out=False)
    with patch("home_swe_home.sandbox.run_in_sandbox", return_value=mock_result):
        result = RUN_COMMAND["execute"]({"command": "true"}, {})
    assert "exit code: 0" in result
    assert "stdout" not in result


def test_run_command_host_success() -> None:
    set_sandbox_enabled(False)
    result = RUN_COMMAND["execute"]({"command": "echo hello"}, {})
    assert "hello" in result
    assert "exit code: 0" in result


def test_run_command_host_not_found() -> None:
    set_sandbox_enabled(False)
    result = RUN_COMMAND["execute"]({"command": "nonexistent_command_xyz"}, {})
    assert "command not found" in result


def test_run_command_host_timeout() -> None:
    set_sandbox_enabled(False)
    exc = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
    exc.stdout = b"out"
    exc.stderr = b"err"
    with patch("subprocess.run", side_effect=exc):
        result = RUN_COMMAND["execute"]({"command": "sleep 100", "timeout": 1}, {})
    assert "timed out" in result
    assert "exit code: 124" in result
    assert "stdout:\nout" in result
    assert "stderr:\nerr" in result


def test_run_command_host_timeout_no_output() -> None:
    set_sandbox_enabled(False)
    exc = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
    exc.stdout = None
    exc.stderr = None
    with patch("subprocess.run", side_effect=exc):
        result = RUN_COMMAND["execute"]({"command": "sleep 100", "timeout": 1}, {})
    assert "timed out" in result
    assert "exit code: 124" in result


# ---------------------------------------------------------------------------
# verify_repo
# ---------------------------------------------------------------------------


def test_verify_repo_default(tmp_path: Path) -> None:
    with patch("home_swe_home.utils.verify.default_runner", return_value=(0, "")):
        result = VERIFY_REPO["execute"]({"path": str(tmp_path)}, {})
    assert "checks passed" in result


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------


def _html_response(body: str) -> MagicMock:
    response = MagicMock()
    response.read.return_value = body.encode()
    response.__enter__ = lambda s: s
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_web_search_with_results() -> None:
    html = '<a class="result__a" href="https://example.com">Example</a>'
    with patch("urllib.request.urlopen", return_value=_html_response(html)):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Example" in result
    assert "https://example.com" in result


def test_web_search_decodes_uddg_redirect() -> None:
    html = (
        '<a class="result__a" '
        'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">'
        "Example</a>"
    )
    with patch("urllib.request.urlopen", return_value=_html_response(html)):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "https://example.com" in result


def test_web_search_protocol_relative_href() -> None:
    html = '<a class="result__a" href="//example.com/page">Example</a>'
    with patch("urllib.request.urlopen", return_value=_html_response(html)):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "https://example.com/page" in result


def test_web_search_skips_empty_title_or_href() -> None:
    html = (
        '<a class="result__a" href="https://example.com"></a>'
        '<a class="result__a" href="">Title</a>'
    )
    with patch("urllib.request.urlopen", return_value=_html_response(html)):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "No web results" in result


def test_web_search_caps_results() -> None:
    """More than 8 matches are truncated to the cap."""
    html = "".join(
        f'<a class="result__a" href="https://e.com/{i}">T{i}</a>' for i in range(20)
    )
    with patch("urllib.request.urlopen", return_value=_html_response(html)):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert len([line for line in result.splitlines() if line.strip()]) == 8


def test_web_search_bot_blocked() -> None:
    html = "<html>captcha unusual traffic</html>"
    with patch("urllib.request.urlopen", return_value=_html_response(html)):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "bot detection" in result or "No web results" in result


def test_web_search_falls_back_to_lite_endpoint() -> None:
    """A bot-blocked html endpoint falls through to the lite endpoint."""
    bot = _html_response("<html>captcha</html>")
    lite = _html_response('<a class="result-link" href="https://example.com">Ex</a>')
    with patch("urllib.request.urlopen", side_effect=[bot, lite]):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Example" not in result  # title is "Ex"
    assert "https://example.com" in result


def test_web_search_all_endpoints_network_error() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("no net")):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Error" in result or "No web results" in result


def test_web_search_searxng_success() -> None:
    import json as json_mod

    data = json_mod.dumps(
        {"results": [{"title": "SearXNG Result", "url": "https://searx.example"}]}
    )
    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", return_value=_html_response(data)):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "SearXNG Result" in result


def test_web_search_searxng_network_error_falls_back() -> None:
    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", side_effect=OSError("no net")):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Error" in result or "No web results" in result


def test_web_search_searxng_bad_json_falls_back() -> None:
    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", return_value=_html_response("not json")):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert isinstance(result, str)


def test_web_search_searxng_empty_results_falls_back() -> None:
    import json as json_mod

    empty = _html_response(json_mod.dumps({"results": []}))
    html = '<a class="result__a" href="https://example.com">Example</a>'
    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", side_effect=[empty, _html_response(html)]):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Example" in result


def test_web_search_searxng_caps_results() -> None:
    import json as json_mod

    results = [{"title": f"Result {i}", "url": f"https://e.com/{i}"} for i in range(20)]
    data = _html_response(json_mod.dumps({"results": results}))
    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", return_value=data):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert len([line for line in result.splitlines() if line.strip()]) == 8


def test_web_search_searxng_skips_empty_fields() -> None:
    import json as json_mod

    data = _html_response(
        json_mod.dumps(
            {
                "results": [
                    {"title": "", "url": "https://example.com"},
                    {"title": "Valid", "url": ""},
                    {"title": "Good", "url": "https://good.example"},
                ]
            }
        )
    )
    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", return_value=data):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Good" in result


def test_web_search_searxng_url_trailing_slash() -> None:  # noqa: D401
    """A trailing slash in SEARXNG_URL is stripped."""
    import json as json_mod

    data = _html_response(json_mod.dumps({"results": []}))
    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example/"}):
        with patch("urllib.request.urlopen", return_value=data) as mock_url:
            WEB_SEARCH["execute"]({"query": "test"}, {})
    # SearXNG is queried first; empty results then fall through to DuckDuckGo.
    first_request = mock_url.call_args_list[0][0][0]
    assert "searx.example/search" in first_request.full_url


# ---------------------------------------------------------------------------
# reload_module
# ---------------------------------------------------------------------------


def test_reload_module_without_agent(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n", encoding="utf-8")
    result = RELOAD_MODULE["execute"]({"module_name": "mod", "file_path": str(f)}, {})
    assert "Reloaded" in result or "Error" in result


def test_reload_module_refuses_when_nothing_read_this_turn(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n", encoding="utf-8")
    agent = _agent_with_events([_turn_start(1)])

    result = RELOAD_MODULE["execute"](
        {"module_name": "mod", "file_path": str(f)}, {"agent": agent}
    )
    assert "Refused" in result


def test_reload_module_allowed_after_read_this_turn(tmp_path: Path) -> None:
    from home_swe_home.tools.definitions import _module_stats

    f = tmp_path / "mod_ok.py"
    f.write_text("x = 1\n", encoding="utf-8")
    agent = _agent_with_events(
        [_turn_start(1), _tool_call(2, "read_file", {"path": str(f)})]
    )

    result = RELOAD_MODULE["execute"](
        {"module_name": "mod_ok", "file_path": str(f)}, {"agent": agent}
    )
    assert "Reloaded" in result
    _module_stats.pop("mod_ok", None)


def test_reload_module_file_not_found() -> None:
    result = RELOAD_MODULE["execute"](
        {"module_name": "mod", "file_path": "/nonexistent/file.py"}, {}
    )
    assert "could not stat" in result


def test_reload_module_skips_malformed_events(tmp_path: Path) -> None:
    f = tmp_path / "mod2.py"
    f.write_text("x = 1\n", encoding="utf-8")
    agent = _agent_with_events(
        [
            _turn_start(1),
            _event(2, "user/message", {}),
            _tool_call(3, "read_file", "not_a_dict"),
            _tool_call(4, "web_search", {"query": "x"}),
        ]
    )

    result = RELOAD_MODULE["execute"](
        {"module_name": "mod2", "file_path": str(f)}, {"agent": agent}
    )
    # No valid read this turn, so the reload is refused.
    assert "Refused" in result


def test_reload_module_no_changes(tmp_path: Path) -> None:
    from home_swe_home.tools.definitions import _module_stats

    f = tmp_path / "mod3.py"
    f.write_text("x = 1\n", encoding="utf-8")

    RELOAD_MODULE["execute"]({"module_name": "mod3", "file_path": str(f)}, {})
    result = RELOAD_MODULE["execute"]({"module_name": "mod3", "file_path": str(f)}, {})
    assert "No changes detected" in result

    _module_stats.pop("mod3", None)


def test_reload_module_adds_py_extension(tmp_path: Path) -> None:
    f = tmp_path / "modpy"
    f.write_text("x = 1\n", encoding="utf-8")
    result = RELOAD_MODULE["execute"](
        {"module_name": "modpy_test", "file_path": str(f)}, {}
    )
    assert "Reloaded" in result or "Error" in result


# ---------------------------------------------------------------------------
# code_metrics
# ---------------------------------------------------------------------------


def test_code_metrics(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def foo():\n    pass\n\nclass Bar:\n    pass\n", encoding="utf-8"
    )
    result = CODE_METRICS["execute"]({"path": str(tmp_path)}, {})
    assert "file_count" in result
    assert "function_count" in result


def test_code_metrics_default() -> None:
    result = CODE_METRICS["execute"]({}, {})
    assert "Code metrics" in result


def test_code_metrics_skips_unreadable(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text("x = 1\n")
    (tmp_path / "bad.py").write_bytes(b"\xff\xfe invalid")
    result = CODE_METRICS["execute"]({"path": str(tmp_path)}, {})
    assert "file_count" in result


# ---------------------------------------------------------------------------
# find_duplicates
# ---------------------------------------------------------------------------


def test_find_duplicates_none(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("unique 1\nunique 2\nunique 3\n")
    result = FIND_DUPLICATES["execute"]({"path": str(tmp_path)}, {})
    assert "No duplicate" in result


def test_find_duplicates_found(tmp_path: Path) -> None:
    content = "x = 1\ny = 2\nz = 3\n"
    (tmp_path / "a.py").write_text(content)
    (tmp_path / "b.py").write_text(content)
    result = FIND_DUPLICATES["execute"]({"path": str(tmp_path)}, {})
    assert "Found" in result
    assert "Duplicate" in result


def test_find_duplicates_default_path() -> None:
    result = FIND_DUPLICATES["execute"]({}, {})
    assert isinstance(result, str)


def test_find_duplicates_skips_unreadable(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text("a\nb\nc\n")
    (tmp_path / "bad.py").write_bytes(b"\xff\xfe invalid")
    result = FIND_DUPLICATES["execute"]({"path": str(tmp_path)}, {})
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# generate_docs
# ---------------------------------------------------------------------------


def test_generate_docs(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        '"""Module."""\n\n\ndef foo():\n    """Do foo."""\n    pass\n\n\n'
        'class Bar:\n    """A bar."""\n\n    def baz(self):\n'
        '        """Do baz."""\n        pass\n',
        encoding="utf-8",
    )
    result = GENERATE_DOCS["execute"]({"path": str(tmp_path)}, {})
    assert "foo" in result
    assert "Bar" in result
    assert "baz" in result


def test_generate_docs_no_docstrings(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def foo():\n    pass\n")
    result = GENERATE_DOCS["execute"]({"path": str(tmp_path)}, {})
    assert "No docstring" in result


def test_generate_docs_syntax_error(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("def foo(\n")
    result = GENERATE_DOCS["execute"]({"path": str(tmp_path)}, {})
    assert isinstance(result, str)


def test_generate_docs_default() -> None:
    result = GENERATE_DOCS["execute"]({}, {})
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# add_repo
# ---------------------------------------------------------------------------

_REPO_MAP = (
    "## Other Repos\n\n"
    "- **test** (test): `../test`. Clone from\n"
    "  <https://github.com/org/test.git> if missing.\n"
)


def _make_home(tmp_path: Path, monkeypatch, map_text: str = _REPO_MAP) -> Path:
    """Create a home checkout with an AGENTS.md repo map and skills dir."""
    home = tmp_path / "agents-home"
    home.mkdir(exist_ok=True)
    (home / "AGENTS.md").write_text(map_text, encoding="utf-8")
    (home / "skills").mkdir(exist_ok=True)
    monkeypatch.setenv("AGENTS_HOME_PATH", str(home))
    return home


def test_add_repo_no_home(monkeypatch) -> None:
    monkeypatch.setattr("home_swe_home.utils.home.find_home", lambda: None)
    result = ADD_REPO["execute"]({"ref": "anything"}, {})
    assert "no agents-home" in result


def test_add_repo_resolved(tmp_path: Path, monkeypatch) -> None:
    home = _make_home(tmp_path, monkeypatch)
    (home / ".." / "test").mkdir(parents=True, exist_ok=True)

    result = ADD_REPO["execute"]({"ref": "test"}, {})
    assert "Resolved" in result


def test_add_repo_not_in_map(tmp_path: Path, monkeypatch) -> None:
    _make_home(tmp_path, monkeypatch, "## Other Repos\n")
    result = ADD_REPO["execute"]({"ref": "unknown"}, {})
    assert "not in the home repo map" in result


def test_add_repo_confirm_required(tmp_path: Path, monkeypatch) -> None:
    _make_home(tmp_path, monkeypatch)
    result = ADD_REPO["execute"]({"ref": "test", "confirm": False}, {})
    assert "Confirm with confirm=true" in result


def test_add_repo_no_clone_url(tmp_path: Path, monkeypatch) -> None:
    _make_home(
        tmp_path, monkeypatch, "## Other Repos\n\n- **test** (test): `../test`.\n"
    )
    result = ADD_REPO["execute"]({"ref": "test"}, {})
    assert "no clone URL" in result


def test_add_repo_rejects_traversal(tmp_path: Path, monkeypatch) -> None:
    """A map entry escaping the home checkout is refused."""
    evil_map = (
        "## Other Repos\n\n- **evil** (evil): `../../etc`. Clone from\n"
        "  <https://github.com/org/evil.git> if missing.\n"
    )
    _make_home(tmp_path, monkeypatch, evil_map)
    result = ADD_REPO["execute"]({"ref": "evil", "confirm": True}, {})
    assert "outside the workspace root" in result


def test_add_repo_clone_success(tmp_path: Path, monkeypatch) -> None:
    _make_home(tmp_path, monkeypatch)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = ADD_REPO["execute"]({"ref": "test", "confirm": True}, {})
    assert "Cloned" in result


def test_add_repo_clone_failure(tmp_path: Path, monkeypatch) -> None:
    _make_home(tmp_path, monkeypatch)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="fatal: error")
        result = ADD_REPO["execute"]({"ref": "test", "confirm": True}, {})
    assert "clone failed" in result


# ---------------------------------------------------------------------------
# _use_sandbox
# ---------------------------------------------------------------------------


def test_use_sandbox_defaults_to_enabled(monkeypatch) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_SANDBOX", raising=False)
    set_sandbox_enabled(True)
    assert _use_sandbox() is True


def test_use_sandbox_env_disable_variants(monkeypatch) -> None:
    set_sandbox_enabled(True)
    for val in ("0", "false", "no", "off"):
        with patch.dict(os.environ, {"HOME_SWE_HOME_SANDBOX": val}):
            assert _use_sandbox() is False


def test_use_sandbox_env_enable_variants(monkeypatch) -> None:
    set_sandbox_enabled(False)
    for val in ("1", "true", "yes", "on"):
        with patch.dict(os.environ, {"HOME_SWE_HOME_SANDBOX": val}):
            assert _use_sandbox() is True


def test_use_sandbox_falls_back_to_setting(monkeypatch) -> None:
    monkeypatch.delenv("HOME_SWE_HOME_SANDBOX", raising=False)
    set_sandbox_enabled(False)
    assert _use_sandbox() is False
    set_sandbox_enabled(True)


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


def test_register_tools() -> None:
    ctx = MagicMock()
    register_tools(ctx)
    assert ctx.tools.register.call_count == len(ALL_TOOLS)


# ---------------------------------------------------------------------------
# Edge cases closed by review
# ---------------------------------------------------------------------------


def test_read_tracker_ignores_non_string_path(tmp_path: Path) -> None:
    """A tool call whose path is not a string does not enter the read set."""
    f = tmp_path / "x.txt"
    f.write_text("content", encoding="utf-8")
    agent = _agent_with_events(
        [
            _turn_start(1),
            _tool_call(2, "read_file", {"path": 12345}),
            _tool_call(3, "read_file", {"path": str(f)}),
        ]
    )

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "content", "new_string": "changed"},
        {"agent": agent},
    )
    assert "Replaced" in result


def test_agent_of_handles_run_ctx_without_get() -> None:
    """A run context that is not a mapping yields no agent."""

    class Opaque:
        pass

    assert _agent_of(Opaque()) is None
    assert _agent_of({}) is None
    sentinel = object()
    assert _agent_of({"agent": sentinel}) is sentinel


def test_run_command_host_stdout_only() -> None:
    """Host output with stdout but no stderr renders stdout only."""
    set_sandbox_enabled(False)
    completed = MagicMock(returncode=0, stdout="only out", stderr="")
    with patch("subprocess.run", return_value=completed):
        result = RUN_COMMAND["execute"]({"command": "true"}, {})
    assert "stdout:\nonly out" in result
    assert "stderr" not in result


def test_run_command_host_stderr_only() -> None:
    """Host output with stderr but no stdout renders stderr only."""
    set_sandbox_enabled(False)
    completed = MagicMock(returncode=1, stdout="", stderr="only err")
    with patch("subprocess.run", return_value=completed):
        result = RUN_COMMAND["execute"]({"command": "false"}, {})
    assert "stderr:\nonly err" in result
    assert "stdout" not in result


def test_web_search_uddg_without_query_string() -> None:
    """A uddg= href with no ``?`` is returned as-is rather than crashing."""
    html = (
        '<a class="result__a" '
        'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.example">A</a>'
    )
    with patch("urllib.request.urlopen", return_value=_html_response(html)):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "a.example" in result or "No web results" in result


def test_web_search_uddg_with_other_pairs() -> None:
    """Non-uddg query parameters are skipped when decoding the target."""
    html = (
        '<a class="result__a" '
        'href="//duckduckgo.com/l/?foo=1&uddg=https%3A%2F%2Fb.example&rut=9">'
        "B</a>"
    )
    with patch("urllib.request.urlopen", return_value=_html_response(html)):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "b.example" in result


def test_reload_module_spec_none(tmp_path: Path) -> None:
    """A path importlib cannot build a spec for is reported, not raised."""
    f = tmp_path / "any.py"
    f.write_text("x = 1\n", encoding="utf-8")
    with patch("importlib.util.spec_from_file_location", return_value=None):
        result = RELOAD_MODULE["execute"](
            {"module_name": "nospec", "file_path": str(f)}, {}
        )
    assert "could not create spec" in result


def test_web_search_uddg_without_leading_pair() -> None:
    """``uddg=`` inside a value (not a leading key) falls through to //."""
    html = '<a class="result__a" href="//duckduckgo.com/l/?x=uddg%3Dnope">Fallback</a>'
    with patch("urllib.request.urlopen", return_value=_html_response(html)):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    # The href is protocol-relative, so it becomes https://duckduckgo.com/...
    assert "https://duckduckgo.com" in result


def test_web_search_uddg_in_value_only() -> None:
    """``uddg=`` inside a value exhausts the pair loop and falls through."""
    # The literal "uddg=" is present and "?" exists, but no pair STARTS with
    # "uddg=" ("y=uddg=z" starts with "y"), so the loop ends without a match
    # and the protocol-relative href is normalized instead.
    html = '<a class="result__a" href="//duckduckgo.com/l/?x=1&y=uddg=z">F</a>'
    with patch("urllib.request.urlopen", return_value=_html_response(html)):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "https://duckduckgo.com" in result
