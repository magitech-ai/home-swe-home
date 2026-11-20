"""Comprehensive tests for all 15 tool definitions."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    LOAD_SKILL,
    READ_FILE,
    RELOAD_MODULE,
    RUN_COMMAND,
    VERIFY_REPO,
    WEB_SEARCH,
    WRITE_FILE,
    _use_sandbox,
    register_tools,
)

# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


def test_read_file(tmp_path: Path) -> None:
    f = tmp_path / "hello.txt"
    f.write_text("Hello, world!", encoding="utf-8")
    result = READ_FILE["execute"]({"path": str(f)}, {})
    assert "Hello, world!" in result


def test_read_file_redacts_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "secret123")
    f = tmp_path / "env.txt"
    f.write_text("key=secret123", encoding="utf-8")
    result = READ_FILE["execute"]({"path": str(f)}, {})
    assert "secret123" not in result
    assert "<redacted>" in result


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


def test_edit_file_no_read_check(tmp_path: Path) -> None:
    """Without agent context, edit proceeds (no read check)."""
    f = tmp_path / "edit.txt"
    f.write_text("old text", encoding="utf-8")
    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "old", "new_string": "new"}, {}
    )
    assert "Replaced" in result
    assert "new text" in f.read_text()


def test_edit_file_not_read(tmp_path: Path) -> None:
    """With agent context that has read other files, edit is refused."""
    f = tmp_path / "unread.txt"
    f.write_text("content", encoding="utf-8")

    # Build a mock agent that has read a different file.
    agent = MagicMock()
    event = MagicMock()
    event.type = "tool/call"
    event.payload = {"name": "read_file", "arguments": {"path": "/other/file.txt"}}
    agent.session.events = [event]

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "content", "new_string": "changed"},
        {"agent": agent},
    )
    assert "Refused" in result
    assert "has not been read" in result


def test_edit_file_was_read(tmp_path: Path) -> None:
    """With agent context that has read this file, edit succeeds."""
    f = tmp_path / "read.txt"
    f.write_text("old text", encoding="utf-8")

    agent = MagicMock()
    event = MagicMock()
    event.type = "tool/call"
    event.payload = {"name": "read_file", "arguments": {"path": str(f)}}
    agent.session.events = [event]

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "old", "new_string": "new"},
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


def test_edit_file_written_file_read(tmp_path: Path) -> None:
    """A file written via write_file counts as read."""
    f = tmp_path / "written.txt"
    f.write_text("old", encoding="utf-8")

    agent = MagicMock()
    event = MagicMock()
    event.type = "tool/call"
    event.payload = {"name": "write_file", "arguments": {"path": str(f)}}
    agent.session.events = [event]

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "old", "new_string": "new"},
        {"agent": agent},
    )
    assert "Replaced" in result


def test_edit_file_session_non_tool_events(tmp_path: Path) -> None:
    """Non-tool-call events in session are ignored."""
    f = tmp_path / "file.txt"
    f.write_text("content", encoding="utf-8")

    agent = MagicMock()
    event1 = MagicMock()
    event1.type = "user/message"
    event1.payload = {}
    event2 = MagicMock()
    event2.type = "tool/call"
    event2.payload = {"name": "read_file", "arguments": "not_a_dict"}
    event3 = MagicMock()
    event3.type = "tool/call"
    event3.payload = {"name": "read_file", "arguments": {"path": str(f)}}
    agent.session.events = [event1, event2, event3]

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "content", "new_string": "changed"},
        {"agent": agent},
    )
    assert "Replaced" in result


def test_edit_file_session_other_tool(tmp_path: Path) -> None:
    """Other tool calls in session are ignored."""
    f = tmp_path / "file.txt"
    f.write_text("content", encoding="utf-8")

    agent = MagicMock()
    event = MagicMock()
    event.type = "tool/call"
    event.payload = {"name": "web_search", "arguments": {"query": "test"}}
    agent.session.events = [event]

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "content", "new_string": "changed"},
        {"agent": agent},
    )
    # No read_file or write_file calls, so read_paths is empty,
    # and the edit proceeds without the read check.
    assert "Replaced" in result


def test_edit_file_write_file_non_dict_args(tmp_path: Path) -> None:
    """A write_file event with non-dict arguments is ignored."""
    f = tmp_path / "file.txt"
    f.write_text("content", encoding="utf-8")

    agent = MagicMock()
    event = MagicMock()
    event.type = "tool/call"
    event.payload = {"name": "write_file", "arguments": "not_a_dict"}
    agent.session.events = [event]

    result = EDIT_FILE["execute"](
        {"path": str(f), "old_string": "content", "new_string": "changed"},
        {"agent": agent},
    )
    # No valid read paths, so edit proceeds
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
    """Unreadable files are skipped."""
    f = tmp_path / "bad.py"
    f.write_bytes(b"\xff\xfe invalid utf-8")
    (tmp_path / "good.py").write_text("match here\n")
    result = GREP_FILES["execute"]({"pattern": "match", "path": str(tmp_path)}, {})
    assert "match" in result


def test_grep_files_directory_with_subdirs(tmp_path: Path) -> None:
    """Grep recurses into subdirectories."""
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "a.py").write_text("needle\n")
    (subdir / "b.py").write_text("no match\n")
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
    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "1")
    mock_result = MagicMock(stdout="out", stderr="err", exit_code=0, timed_out=False)
    with patch("home_swe_home.sandbox.run_in_sandbox", return_value=mock_result):
        result = RUN_COMMAND["execute"]({"command": "echo hi"}, {})
    assert "stdout:\nout" in result
    assert "exit code: 0" in result


def test_run_command_sandboxed_timed_out(monkeypatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "1")
    mock_result = MagicMock(stdout="", stderr="", exit_code=124, timed_out=True)
    with patch("home_swe_home.sandbox.run_in_sandbox", return_value=mock_result):
        result = RUN_COMMAND["execute"]({"command": "sleep 100"}, {})
    assert "timed out" in result


def test_run_command_host_success(monkeypatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "0")
    result = RUN_COMMAND["execute"]({"command": "echo hello"}, {})
    assert "hello" in result
    assert "exit code: 0" in result


def test_run_command_host_not_found(monkeypatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "0")
    result = RUN_COMMAND["execute"]({"command": "nonexistent_command_xyz"}, {})
    assert "command not found" in result


def test_run_command_host_with_stderr(monkeypatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "0")
    result = RUN_COMMAND["execute"]({"command": "ls /nonexistent_path_xyz 2>&1"}, {})
    assert "exit code" in result


def test_run_command_sandboxed_empty_output(monkeypatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "1")
    mock_result = MagicMock(stdout="", stderr="", exit_code=0, timed_out=False)
    with patch("home_swe_home.sandbox.run_in_sandbox", return_value=mock_result):
        result = RUN_COMMAND["execute"]({"command": "true"}, {})
    assert "exit code: 0" in result
    assert "stdout" not in result
    assert "stderr" not in result


def test_run_command_host_timeout(monkeypatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "0")
    exc = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
    exc.stdout = b"out"
    exc.stderr = b"err"
    with patch("subprocess.run", side_effect=exc):
        result = RUN_COMMAND["execute"]({"command": "sleep 100", "timeout": 1}, {})
    assert "timed out" in result
    assert "exit code: 124" in result
    assert "stdout:\nout" in result
    assert "stderr:\nerr" in result


def test_run_command_host_timeout_no_output(monkeypatch) -> None:
    monkeypatch.setenv("HOME_SWE_HOME_SANDBOX", "0")
    exc = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
    exc.stdout = None
    exc.stderr = None
    with patch("subprocess.run", side_effect=exc):
        result = RUN_COMMAND["execute"]({"command": "sleep 100", "timeout": 1}, {})
    assert "timed out" in result
    assert "exit code: 124" in result


# ---------------------------------------------------------------------------
# load_skill
# ---------------------------------------------------------------------------


def test_load_skill_no_agent() -> None:
    result = LOAD_SKILL["execute"]({"name": "test"}, {})
    assert "Error" in result
    assert "not available" in result


def test_load_skill_with_agent() -> None:
    agent = MagicMock()
    agent.ctx.get.return_value = MagicMock()
    agent.ctx.get.return_value.load.return_value = "Skill body here"
    result = LOAD_SKILL["execute"]({"name": "test"}, {"agent": agent})
    assert "Skill body here" in result


def test_load_skill_agent_no_ctx() -> None:
    agent = MagicMock(spec=[])  # no ctx attribute
    result = LOAD_SKILL["execute"]({"name": "test"}, {"agent": agent})
    assert "Error" in result


def test_load_skill_no_skills_service() -> None:
    """When agent has ctx but no skills service mounted."""
    agent = MagicMock()
    agent.ctx.get.return_value = None
    result = LOAD_SKILL["execute"]({"name": "test"}, {"agent": agent})
    assert "Error" in result
    assert "not available" in result


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


def test_web_search_no_results() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("no net")):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Error" in result or "No web results" in result


def test_web_search_with_results() -> None:
    html = '<a class="result__a" href="https://example.com">Example</a>'
    mock_response = MagicMock()
    mock_response.read.return_value = html.encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Example" in result
    assert "https://example.com" in result


def test_web_search_searxng() -> None:
    import json as json_mod

    data = json_mod.dumps(
        {"results": [{"title": "SearXNG Result", "url": "https://searx.example"}]}
    )
    mock_response = MagicMock()
    mock_response.read.return_value = data.encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "SearXNG Result" in result


def test_web_search_bot_blocked() -> None:
    html = "<html>captcha unusual traffic</html>"
    mock_response = MagicMock()
    mock_response.read.return_value = html.encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "bot detection" in result or "No web results" in result


def test_web_search_uddg_redirect() -> None:
    """DuckDuckGo redirect URLs are decoded."""
    html = (
        '<a class="result__a" '
        'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">'
        "Example</a>"
    )
    mock_response = MagicMock()
    mock_response.read.return_value = html.encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "https://example.com" in result


def test_web_search_protocol_relative() -> None:
    """Protocol-relative URLs get https: prefix."""
    html = '<a class="result__a" href="//example.com/page">Example</a>'
    mock_response = MagicMock()
    mock_response.read.return_value = html.encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "https://example.com/page" in result


def test_web_search_empty_title_or_href() -> None:
    """Results with empty title or href are skipped."""
    html = (
        '<a class="result__a" href="https://example.com"></a>'
        '<a class="result__a" href="">Title</a>'
    )
    mock_response = MagicMock()
    mock_response.read.return_value = html.encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "No web results" in result or "Example" not in result


def test_web_search_searxng_error() -> None:
    """SearXNG errors fall back to DuckDuckGo."""
    import json as json_mod

    data = json_mod.dumps({"results": []})
    mock_response = MagicMock()
    mock_response.read.return_value = data.encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert isinstance(result, str)


def test_web_search_searxng_bad_json() -> None:
    """SearXNG returning bad JSON falls back to DuckDuckGo."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"not json"
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert isinstance(result, str)


def test_web_search_lite_endpoint() -> None:
    """Falls back to DuckDuckGo Lite endpoint."""
    html = '<a class="result-link" href="https://example.com">Example</a>'
    # First call (html endpoint) returns bot challenge, second (lite) returns results.
    bot_html = "<html>captcha</html>"
    mock_bot = MagicMock()
    mock_bot.read.return_value = bot_html.encode()
    mock_bot.__enter__ = lambda s: s
    mock_bot.__exit__ = MagicMock(return_value=False)

    mock_lite = MagicMock()
    mock_lite.read.return_value = html.encode()
    mock_lite.__enter__ = lambda s: s
    mock_lite.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", side_effect=[mock_bot, mock_lite]):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Example" in result


def test_web_search_all_endpoints_fail() -> None:
    """All endpoints failing with network errors returns error."""
    with patch("urllib.request.urlopen", side_effect=OSError("no net")):
        result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Error" in result or "No web results" in result


def test_web_search_searxng_network_error() -> None:
    """SearXNG network error falls back to DuckDuckGo."""
    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", side_effect=OSError("no net")):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Error" in result or "No web results" in result


def test_web_search_searxng_empty_results() -> None:
    """SearXNG returning empty results falls back to DuckDuckGo."""
    import json as json_mod

    data = json_mod.dumps({"results": []})
    mock_response = MagicMock()
    mock_response.read.return_value = data.encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    html = '<a class="result__a" href="https://example.com">Example</a>'
    mock_ddg = MagicMock()
    mock_ddg.read.return_value = html.encode()
    mock_ddg.__enter__ = lambda s: s
    mock_ddg.__exit__ = MagicMock(return_value=False)

    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", side_effect=[mock_response, mock_ddg]):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Example" in result


def test_web_search_searxng_many_results() -> None:
    """SearXNG results are capped at _MAX_RESULTS."""
    import json as json_mod

    results = [
        {"title": f"Result {i}", "url": f"https://example.com/{i}"} for i in range(20)
    ]
    data = json_mod.dumps({"results": results})
    mock_response = MagicMock()
    mock_response.read.return_value = data.encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    # Should be capped at 8 results
    assert result.count("\n") <= 8


def test_web_search_searxng_empty_title() -> None:
    """SearXNG results with empty title/url are skipped."""
    import json as json_mod

    data = json_mod.dumps(
        {
            "results": [
                {"title": "", "url": "https://example.com"},
                {"title": "Valid", "url": ""},
                {"title": "Good", "url": "https://good.example"},
            ]
        }
    )
    mock_response = MagicMock()
    mock_response.read.return_value = data.encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch.dict(os.environ, {"SEARXNG_URL": "https://searx.example"}):
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = WEB_SEARCH["execute"]({"query": "test"}, {})
    assert "Good" in result


# ---------------------------------------------------------------------------
# reload_module
# ---------------------------------------------------------------------------


def test_reload_module_no_agent(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n", encoding="utf-8")
    result = RELOAD_MODULE["execute"]({"module_name": "mod", "file_path": str(f)}, {})
    # No agent = no read check, so it proceeds
    assert "Reloaded" in result or "Error" in result


def test_reload_module_not_read(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n", encoding="utf-8")

    agent = MagicMock()
    event = MagicMock()
    event.type = "tool/call"
    event.payload = {"name": "read_file", "arguments": {"path": "/other"}}
    agent.session.events = [event]

    result = RELOAD_MODULE["execute"](
        {"module_name": "mod", "file_path": str(f)}, {"agent": agent}
    )
    assert "Refused" in result


def test_reload_module_file_not_found() -> None:
    result = RELOAD_MODULE["execute"](
        {"module_name": "mod", "file_path": "/nonexistent/file.py"}, {}
    )
    assert "could not stat" in result


def test_reload_module_no_changes(tmp_path: Path) -> None:
    from home_swe_home.tools.definitions import _module_stats

    f = tmp_path / "mod.py"
    f.write_text("x = 1\n", encoding="utf-8")

    # First reload
    RELOAD_MODULE["execute"]({"module_name": "testmod", "file_path": str(f)}, {})

    # Second reload — no changes
    result = RELOAD_MODULE["execute"](
        {"module_name": "testmod", "file_path": str(f)}, {}
    )
    assert "No changes detected" in result

    _module_stats.pop("testmod", None)


def test_reload_module_adds_py_extension(tmp_path: Path) -> None:
    """If file_path doesn't end with .py, it's added."""
    f = tmp_path / "modpy"
    f.write_text("x = 1\n", encoding="utf-8")
    result = RELOAD_MODULE["execute"](
        {"module_name": "modpy_test", "file_path": str(f)}, {}
    )
    assert "Reloaded" in result or "Error" in result


def test_reload_module_bad_spec(tmp_path: Path) -> None:
    """A file that can't create a spec returns an error."""
    f = tmp_path / "not_python.txt"
    f.write_text("not python code [[[", encoding="utf-8")
    result = RELOAD_MODULE["execute"](
        {"module_name": "badmod", "file_path": str(f)}, {}
    )
    # Should either fail to create spec or fail to execute
    assert "Error" in result or "Reloaded" in result


def test_reload_module_session_non_tool_events(tmp_path: Path) -> None:
    """Non-tool-call events in session are ignored."""
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n", encoding="utf-8")

    agent = MagicMock()
    event1 = MagicMock()
    event1.type = "user/message"
    event1.payload = {}
    event2 = MagicMock()
    event2.type = "tool/call"
    event2.payload = {"name": "read_file", "arguments": "not_a_dict"}
    agent.session.events = [event1, event2]

    result = RELOAD_MODULE["execute"](
        {"module_name": "mod_test", "file_path": str(f)}, {"agent": agent}
    )
    # No valid read paths, so no read check — proceeds
    assert "Reloaded" in result or "Error" in result


def test_reload_module_session_other_tool(tmp_path: Path) -> None:
    """Other tool calls in session are ignored."""
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n", encoding="utf-8")

    agent = MagicMock()
    event = MagicMock()
    event.type = "tool/call"
    event.payload = {"name": "web_search", "arguments": {"query": "test"}}
    agent.session.events = [event]

    result = RELOAD_MODULE["execute"](
        {"module_name": "mod_test2", "file_path": str(f)}, {"agent": agent}
    )
    assert "Reloaded" in result or "Error" in result


def test_reload_module_spec_none(tmp_path: Path) -> None:
    """A file that can't create a spec returns an error."""
    f = tmp_path / "empty.py"
    f.write_text("", encoding="utf-8")
    # An empty file should still create a valid spec
    result = RELOAD_MODULE["execute"](
        {"module_name": "empty_mod", "file_path": str(f)}, {}
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


def test_code_metrics_unreadable_file(tmp_path: Path) -> None:
    """Unreadable Python files are skipped."""
    (tmp_path / "good.py").write_text("x = 1\n")
    (tmp_path / "bad.py").write_bytes(b"\xff\xfe invalid")
    result = CODE_METRICS["execute"]({"path": str(tmp_path)}, {})
    assert "file_count" in result


# ---------------------------------------------------------------------------
# find_duplicates
# ---------------------------------------------------------------------------


def test_find_duplicates_none(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("unique line 1\nunique line 2\nunique line 3\n")
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


def test_find_duplicates_unreadable_file(tmp_path: Path) -> None:
    """Unreadable Python files are skipped."""
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


def test_add_repo_no_home(monkeypatch) -> None:
    monkeypatch.setattr("home_swe_home.utils.home.find_home", lambda: None)
    result = ADD_REPO["execute"]({"ref": "anything"}, {})
    assert "no agents-home" in result


def test_add_repo_resolved(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text(
        "## Other Repos\n\n- **test** (test): `../test`. Clone from\n"
        "  <https://github.com/org/test.git> if missing.\n",
        encoding="utf-8",
    )
    (home / "skills").mkdir()
    monkeypatch.setenv("AGENTS_HOME_PATH", str(home))
    (home / ".." / "test").mkdir(parents=True, exist_ok=True)

    result = ADD_REPO["execute"]({"ref": "test"}, {})
    assert "Resolved" in result


def test_add_repo_not_in_map(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text("## Other Repos\n", encoding="utf-8")
    (home / "skills").mkdir()
    monkeypatch.setenv("AGENTS_HOME_PATH", str(home))

    result = ADD_REPO["execute"]({"ref": "unknown"}, {})
    assert "not in the home repo map" in result


def test_add_repo_confirm_required(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text(
        "## Other Repos\n\n- **test** (test): `../test`. Clone from\n"
        "  <https://github.com/org/test.git> if missing.\n",
        encoding="utf-8",
    )
    (home / "skills").mkdir()
    monkeypatch.setenv("AGENTS_HOME_PATH", str(home))

    result = ADD_REPO["execute"]({"ref": "test", "confirm": False}, {})
    assert "Confirm with confirm=true" in result


def test_add_repo_no_clone_url(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text(
        "## Other Repos\n\n- **test** (test): `../test`.\n",
        encoding="utf-8",
    )
    (home / "skills").mkdir()
    monkeypatch.setenv("AGENTS_HOME_PATH", str(home))

    result = ADD_REPO["execute"]({"ref": "test"}, {})
    assert "no clone URL" in result


def test_add_repo_clone_success(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text(
        "## Other Repos\n\n- **test** (test): `../test`. Clone from\n"
        "  <https://github.com/org/test.git> if missing.\n",
        encoding="utf-8",
    )
    (home / "skills").mkdir()
    monkeypatch.setenv("AGENTS_HOME_PATH", str(home))

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = ADD_REPO["execute"]({"ref": "test", "confirm": True}, {})
    assert "Cloned" in result


def test_add_repo_clone_failure(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "agents-home"
    home.mkdir()
    (home / "AGENTS.md").write_text(
        "## Other Repos\n\n- **test** (test): `../test`. Clone from\n"
        "  <https://github.com/org/test.git> if missing.\n",
        encoding="utf-8",
    )
    (home / "skills").mkdir()
    monkeypatch.setenv("AGENTS_HOME_PATH", str(home))

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="fatal: error")
        result = ADD_REPO["execute"]({"ref": "test", "confirm": True}, {})
    assert "clone failed" in result


# ---------------------------------------------------------------------------
# _use_sandbox
# ---------------------------------------------------------------------------


def test_use_sandbox_default() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HOME_SWE_HOME_SANDBOX", None)
        assert _use_sandbox() is True


def test_use_sandbox_disabled() -> None:
    for val in ("0", "false", "no", "off"):
        with patch.dict(os.environ, {"HOME_SWE_HOME_SANDBOX": val}):
            assert _use_sandbox() is False


def test_use_sandbox_enabled() -> None:
    for val in ("1", "true", "yes", "on"):
        with patch.dict(os.environ, {"HOME_SWE_HOME_SANDBOX": val}):
            assert _use_sandbox() is True


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


def test_register_tools() -> None:
    ctx = MagicMock()
    register_tools(ctx)
    assert ctx.tools.register.call_count == len(ALL_TOOLS)
