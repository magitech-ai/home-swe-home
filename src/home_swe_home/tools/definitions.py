"""mth tool definitions for home-swe-home.

Each tool is a ``ToolDefinition`` registered on ``ctx.tools`` via
``ctx.tools.register(define_tool({...}))``. The execute handlers receive
``(args, run_ctx)`` where ``run_ctx`` carries ``signal``, ``callId``, ``agent``,
``deferContext``, and ``concludeTurn`` from mth's tool pipeline.

The ``read_files`` tracker from the original anima-based tools is replaced by
mth's ``agent`` reference in ``run_ctx`` — tools that need to check whether a
file has been read can access the agent's session and working directory.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import re
import shlex
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Any

from magitech_harness.tools import define_tool

from ..utils.secrets import redact
from ..utils.text import decode_text

# ---------------------------------------------------------------------------
# Helper: build a standard text-output tool definition
# ---------------------------------------------------------------------------

def _text_output_tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    execute: Any,
    concurrency_safe: bool = False,
) -> dict[str, Any]:
    """Build a ToolDefinition that returns plain text output."""
    result: dict[str, Any] = define_tool({
        "name": name,
        "description": description,
        "parameters": parameters,
        "isConcurrencySafe": lambda _args: concurrency_safe,
        "output": {
            "schema": {"type": "string"},
            "render": lambda _args, val: [{"type": "text", "text": val}],
        },
        "execute": execute,
    })
    return result


# ---------------------------------------------------------------------------
# File tools
# ---------------------------------------------------------------------------

def _read_file_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    path = args["path"]
    return redact(Path(path).read_text(encoding="utf-8"))


READ_FILE = _text_output_tool(
    name="read_file",
    description=(
        "Read a file and return its text contents.\n\n"
        "Reading a file marks it as readable, which is required before calling\n"
        "edit_file on that path."
    ),
    parameters={
        "path": {"type": "string", "required": True},
    },
    execute=_read_file_execute,
    concurrency_safe=True,
)


def _write_file_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    path = args["path"]
    content = args["content"]
    Path(path).write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}."


WRITE_FILE = _text_output_tool(
    name="write_file",
    description=(
        "Create or overwrite a file with the given text. After writing, the path\n"
        "is marked readable so it can be edited with edit_file."
    ),
    parameters={
        "path": {"type": "string", "required": True},
        "content": {"type": "string", "required": True},
    },
    execute=_write_file_execute,
)


def _edit_file_execute(args: dict[str, Any], run_ctx: Any) -> str:
    path = args["path"]
    old_string = args["old_string"]
    new_string = args["new_string"]

    # Check if the file has been read in this session.
    session = run_ctx.get("agent")
    read_paths: set[str] = set()
    if session is not None:
        for event in session.session.events:
            if event.type == "tool/call" and event.payload.get("name") == "read_file":
                call_args = event.payload.get("arguments")
                if isinstance(call_args, dict):
                    read_paths.add(str(call_args.get("path", "")))
            elif event.type == "tool/call" and event.payload.get(
                "name"
            ) == "write_file":
                call_args = event.payload.get("arguments")
                if isinstance(call_args, dict):
                    read_paths.add(str(call_args.get("path", "")))

    if read_paths and path not in read_paths:
        return (
            f"Refused: '{path}' has not been read yet. "
            f"Call read_file on '{path}' first, then retry edit_file."
        )

    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old_string not in text:
        return (
            f"Error: old_string not found in {path}. "
            f"Call read_file on {path} to see the exact text (including "
            f"whitespace and indentation), then call edit_file again with "
            f"an exact old_string."
        )
    target.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
    return f"Replaced the first occurrence of old_string in {path}."


EDIT_FILE = _text_output_tool(
    name="edit_file",
    description=(
        "Replace exact text in a file you have already read. Replaces the first\n"
        "occurrence of old_string with new_string."
    ),
    parameters={
        "path": {"type": "string", "required": True},
        "old_string": {"type": "string", "required": True},
        "new_string": {"type": "string", "required": True},
    },
    execute=_edit_file_execute,
)


def _delete_file_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    path = args["path"]
    target = Path(path)
    try:
        target.unlink()
    except FileNotFoundError:
        return f"Error: FileNotFoundError: No such file or directory: '{path}'"
    return f"Deleted {path}."


DELETE_FILE = _text_output_tool(
    name="delete_file",
    description="Delete a file. Only files that exist can be deleted.",
    parameters={
        "path": {"type": "string", "required": True},
    },
    execute=_delete_file_execute,
)


def _list_directory_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    path = args.get("path", ".")
    entries = sorted(Path(path).iterdir())
    lines: list[str] = []
    for entry in entries:
        lines.append(f"{entry.name}/" if entry.is_dir() else entry.name)
    return "\n".join(lines) if lines else "(empty)"


LIST_DIRECTORY = _text_output_tool(
    name="list_directory",
    description="List the entries of a directory.",
    parameters={
        "path": {"type": "string"},
    },
    execute=_list_directory_execute,
    concurrency_safe=True,
)


def _grep_files_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    pattern = args["pattern"]
    path = args.get("path", ".")
    regex = re.compile(pattern)
    root = Path(path)
    matches: list[str] = []

    if root.is_file():
        files_to_search: list[Path] = [root]
    else:
        files_to_search = list(root.rglob("*"))

    for file in files_to_search:
        if not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{file}:{line_number}: {line}")
                if len(matches) >= 50:
                    break
        if len(matches) >= 50:
            break
    return "\n".join(matches) if matches else "No matches."


GREP_FILES = _text_output_tool(
    name="grep_files",
    description=(
        "Search files for a regex pattern.\n\n"
        "Returns matching lines with file:line:content, capped at 50 matches."
    ),
    parameters={
        "pattern": {"type": "string", "required": True},
        "path": {"type": "string"},
    },
    execute=_grep_files_execute,
    concurrency_safe=True,
)


# ---------------------------------------------------------------------------
# Shell tool
# ---------------------------------------------------------------------------

_SANDBOX_ENV = "HOME_SWE_HOME_SANDBOX"


def _use_sandbox() -> bool:
    return os.environ.get(_SANDBOX_ENV, "").lower() in ("1", "true", "yes", "on")


def _run_command_execute(args: dict[str, Any], run_ctx: Any) -> str:
    command = args["command"]
    timeout = int(args.get("timeout", 30))

    if _use_sandbox():
        from ..sandbox import run_in_sandbox
        result = run_in_sandbox(command, timeout=timeout)
        sandbox_parts: list[str] = []
        if result.stdout:
            sandbox_parts.append(f"stdout:\n{result.stdout}")
        if result.stderr:
            sandbox_parts.append(f"stderr:\n{result.stderr}")
        sandbox_parts.append(f"exit code: {result.exit_code}")
        if result.timed_out:
            sandbox_parts.append("timed out")
        return "\n".join(sandbox_parts)

    # Host mode — use subprocess with timeout.
    try:
        completed = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        return (
            f"Error: command not found: {error.filename}. "
            "Check the command and retry."
        )
    except subprocess.TimeoutExpired as error:
        stdout = decode_text(getattr(error, "stdout", None))
        stderr = decode_text(getattr(error, "stderr", None))
        timeout_parts: list[str] = []
        if stdout:
            timeout_parts.append(f"stdout:\n{stdout}")
        if stderr:
            timeout_parts.append(f"stderr:\n{stderr}")
        timeout_parts.append("exit code: 124")
        timeout_parts.append("timed out")
        return "\n".join(timeout_parts)
    parts: list[str] = []
    if completed.stdout:
        parts.append(f"stdout:\n{completed.stdout}")
    if completed.stderr:
        parts.append(f"stderr:\n{completed.stderr}")
    parts.append(f"exit code: {completed.returncode}")
    return "\n".join(parts)


RUN_COMMAND = _text_output_tool(
    name="run_command",
    description=(
        "Run a shell command on the host (default) or in a Docker sandbox.\n\n"
        "By default the command runs directly on the host with a timeout. Set\n"
        "``HOME_SWE_HOME_SANDBOX=1`` to run inside a throwaway Docker container.\n\n"
        "Security note: unsandboxed commands run with the user's privileges,\n"
        "including access to environment variables such as NVIDIA_API_KEY."
    ),
    parameters={
        "command": {"type": "string", "required": True},
        "timeout": {"type": "integer"},
    },
    execute=_run_command_execute,
)


# ---------------------------------------------------------------------------
# Skill tool
# ---------------------------------------------------------------------------

def _load_skill_execute(args: dict[str, Any], run_ctx: Any) -> str:
    name = args["name"]
    skills = run_ctx.get("agent")
    if skills is not None:
        # Access the skills service through the agent's context.
        ctx = run_ctx.get("agent")
        if ctx is not None and hasattr(ctx, "ctx"):
            skills_svc = ctx.ctx.get("skills", None, strict=False)
            if skills_svc is not None:
                return str(skills_svc.load(name))
    return f"Error: skill '{name}' is not available."


LOAD_SKILL = _text_output_tool(
    name="load_skill",
    description="Load the named skill's full instructions into context.",
    parameters={
        "name": {"type": "string", "required": True},
    },
    execute=_load_skill_execute,
)


# ---------------------------------------------------------------------------
# Repo verification tool
# ---------------------------------------------------------------------------

def _verify_repo_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    from ..utils.verify import (
        default_runner,
        format_results,
        run_checks,
        verification_commands,
    )
    path = args.get("path", ".")
    root = Path(path).resolve()
    return format_results(
        run_checks(verification_commands(root), default_runner, cwd=root)
    )


VERIFY_REPO = _text_output_tool(
    name="verify_repo",
    description=(
        "Run this repository's declared checks and report pass/fail.\n\n"
        "Call this on every affected repository before reporting a multi-repo\n"
        "task as done."
    ),
    parameters={
        "path": {"type": "string"},
    },
    execute=_verify_repo_execute,
)


# ---------------------------------------------------------------------------
# Web search tool
# ---------------------------------------------------------------------------

def _web_search_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    import html as html_mod
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    _MAX_RESULTS = 8
    _TIMEOUT = 15
    _UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    _SEARXNG_ENV = "SEARXNG_URL"

    _ENDPOINTS = [
        (
            "https://html.duckduckgo.com/html/?{}",
            re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                re.DOTALL,
            ),
        ),
        (
            "https://lite.duckduckgo.com/lite/?{}",
            re.compile(
                r'<a[^>]*class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                re.DOTALL,
            ),
        ),
    ]

    _BOT_SIGNALS = ("captcha", "unusual traffic", "anomaly")

    def _is_bot_challenge(page: str) -> bool:
        lower = page.lower()
        if any(signal in lower for signal in _BOT_SIGNALS):
            return True
        return "blocked" in lower and "requests" in lower

    def _decode_href(href: str) -> str:
        href = html_mod.unescape(href)
        if "uddg=" in href:
            query = href.split("?", 1)[1] if "?" in href else ""
            for pair in query.split("&"):
                if pair.startswith("uddg="):
                    return urllib.parse.unquote(pair[len("uddg="):])
        if href.startswith("//"):
            return "https:" + href
        return href

    def _parse_results(page: str, pattern: re.Pattern[str]) -> list[str]:
        results: list[str] = []
        for match in pattern.finditer(page):
            href = _decode_href(match.group(1))
            title = html_mod.unescape(
                re.sub(r"<.*?>", "", match.group(2))
            ).strip()
            if title and href:
                results.append(f"{title}: {href}")
            if len(results) >= _MAX_RESULTS:
                break
        return results

    def _searxng_url() -> str | None:
        return (os.environ.get(_SEARXNG_ENV) or "").strip().rstrip("/") or None

    def _search_searxng(base_url: str, query: str) -> list[str] | None:
        params = urllib.parse.urlencode({"q": query, "format": "json"})
        url = f"{base_url}/search?{params}"
        req = urllib.request.Request(url, headers=_UA)
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, OSError):
            return None
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None
        results: list[str] = []
        for item in data.get("results", []):
            title = str(item.get("title", "")).strip()
            href = str(item.get("url", "")).strip()
            if title and href:
                results.append(f"{title}: {href}")
            if len(results) >= _MAX_RESULTS:
                break
        return results

    query = args["query"]
    base_url = _searxng_url()
    if base_url:
        results = _search_searxng(base_url, query)
        if results:
            return "\n".join(results)

    encoded = urllib.parse.urlencode({"q": query})
    bot_blocked = False
    network_errors: list[str] = []

    for template, pattern in _ENDPOINTS:
        url = template.format(encoded)
        req = urllib.request.Request(url, headers=_UA)
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as response:
                page = response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError) as error:
            network_errors.append(str(error))
            continue

        if _is_bot_challenge(page):
            bot_blocked = True
            continue

        results = _parse_results(page, pattern)
        if results:
            return "\n".join(results)

    if network_errors and not bot_blocked:
        return (
            f"Error: web search failed: {network_errors[-1]}. "
            "Check your network connection and retry the query."
        )
    if bot_blocked:
        return (
            "Error: web search failed: DuckDuckGo is blocking automated "
            "requests (bot detection). Try again later or use a different "
            "query."
        )
    return "No web results found. Try rephrasing the query."


WEB_SEARCH = _text_output_tool(
    name="web_search",
    description=(
        "Search the web via SearXNG (if configured) or DuckDuckGo.\n\n"
        "With ``SEARXNG_URL`` set, uses that instance's JSON API first (reliable,\n"
        "no key, no bot detection); falls back to DuckDuckGo."
    ),
    parameters={
        "query": {"type": "string", "required": True},
    },
    execute=_web_search_execute,
)


# ---------------------------------------------------------------------------
# Module reload tool
# ---------------------------------------------------------------------------

_module_stats: dict[str, tuple[float, int]] = {}


def _reload_module_execute(args: dict[str, Any], run_ctx: Any) -> str:
    module_name = args["module_name"]
    file_path = args["file_path"]

    # Check read_files via session tool history.
    agent = run_ctx.get("agent")
    read_paths: set[str] = set()
    if agent is not None:
        for event in agent.session.events:
            if event.type == "tool/call" and event.payload.get(
                "name"
            ) in ("read_file", "write_file"):
                call_args = event.payload.get("arguments")
                if isinstance(call_args, dict):
                    read_paths.add(str(call_args.get("path", "")))

    if read_paths and file_path not in read_paths:
        return (
            f"Refused: '{file_path}' has not been read yet. "
            f"Call read_file on '{file_path}' first, then retry reload_module."
        )

    path = os.path.abspath(file_path)
    if not path.endswith(".py"):
        path = path + ".py"
    try:
        stat = os.stat(path)
    except OSError:
        return f"Error: could not stat {path}."
    current = (stat.st_mtime, stat.st_size)

    cached = _module_stats.get(module_name)
    if cached is not None and cached == current:
        return (
            f"No changes detected for module '{module_name}' "
            f"since last reload (mtime={cached[0]:.1f})."
        )

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return f"Error: could not create spec for {path}."
    with suppress(ValueError, OSError):
        Path(importlib.util.cache_from_source(path)).unlink(missing_ok=True)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _module_stats[module_name] = current
    return f"Reloaded module '{module_name}' from {path} (mtime={current[0]:.1f})."


RELOAD_MODULE = _text_output_tool(
    name="reload_module",
    description=(
        "Hot-reload a Python module from disk.\n\n"
        "Picks up any changes made since the last import."
    ),
    parameters={
        "module_name": {"type": "string", "required": True},
        "file_path": {"type": "string", "required": True},
    },
    execute=_reload_module_execute,
)


# ---------------------------------------------------------------------------
# Code metrics tool
# ---------------------------------------------------------------------------

def _code_metrics_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    path = args.get("path", ".")
    root = Path(path)
    py_files = list(root.rglob("*.py"))

    total_lines = 0
    blank_lines = 0
    comment_lines = 0
    function_count = 0
    class_count = 0
    file_count = 0
    complexity_total = 0

    complexity_keywords = {"if", "elif", "for", "while", "try", "except"}

    for py_file in py_files:
        file_count += 1
        try:
            text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        lines = text.splitlines()
        total_lines += len(lines)

        blank_lines += sum(1 for line in lines if line.strip() == "")
        comment_lines += sum(1 for line in lines if line.strip().startswith("#"))

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("class "):
                class_count += 1
            elif stripped.startswith("def ") and not line.startswith((" ", "\t")):
                function_count += 1

        for keyword in complexity_keywords:
            complexity_total += len(re.findall(rf"\b{keyword}\b", text))

    metrics = {
        "file_count": file_count,
        "total_lines": total_lines,
        "blank_lines": blank_lines,
        "comment_lines": comment_lines,
        "net_lines": total_lines - blank_lines - comment_lines,
        "function_count": function_count,
        "class_count": class_count,
        "estimated_complexity": complexity_total,
    }

    return f"Code metrics for {path}:\n" + "\n".join(
        f"  {k}: {v}" for k, v in metrics.items()
    )


CODE_METRICS = _text_output_tool(
    name="code_metrics",
    description=(
        "Calculate code quality metrics for Python files in a directory.\n\n"
        "Returns lines of code, cyclomatic complexity estimates, and other metrics."
    ),
    parameters={
        "path": {"type": "string"},
    },
    execute=_code_metrics_execute,
    concurrency_safe=True,
)


# ---------------------------------------------------------------------------
# Find duplicates tool
# ---------------------------------------------------------------------------

def _find_duplicates_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    path = args.get("path", "")
    if not path:
        path = "."
    min_lines = int(args.get("min_lines", 3))

    root = Path(path)
    py_files: list[Path] = list(root.rglob("*.py"))

    file_lines: dict[Path, list[str]] = {}
    for f in py_files:
        try:
            text = f.read_text(encoding="utf-8")
            file_lines[f] = text.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

    seen: dict[str, list[tuple[Path, int]]] = {}

    for f, lines in file_lines.items():
        for start in range(len(lines) - min_lines + 1):
            block = "\n".join(lines[start : start + min_lines])
            seen.setdefault(block, []).append((f, start + 1))

    duplicates: list[str] = []
    for block, locations in seen.items():
        if len(locations) > 1:
            duplicates.append(
                f"Duplicate block ({min_lines} lines):\n"
                + "\n".join(f"  {loc[0].name}:{loc[1]}" for loc in locations[:5])
                + f"\n  {block[:100]}...\n"
            )

    if not duplicates:
        return "No duplicate code blocks found."

    return f"Found {len(duplicates)} duplicate code blocks:\n" + "\n".join(duplicates)


FIND_DUPLICATES = _text_output_tool(
    name="find_duplicates",
    description=(
        "Find duplicate code blocks across Python files.\n\n"
        "Uses simple line-based comparison to find near-identical code sequences."
    ),
    parameters={
        "path": {"type": "string"},
        "min_lines": {"type": "integer"},
    },
    execute=_find_duplicates_execute,
    concurrency_safe=True,
)


# ---------------------------------------------------------------------------
# Generate docs tool
# ---------------------------------------------------------------------------

def _generate_docs_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    path = args.get("path", ".")
    root = Path(path)
    py_files = list(root.rglob("*.py"))

    docs_lines: list[str] = []
    docs_lines.append(f"# Auto-generated Documentation for {path}")
    docs_lines.append("")
    docs_lines.append("_Generated by home-swe-home recursive improvement tools_")
    docs_lines.append("")

    for py_file in py_files:
        try:
            text = py_file.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue

        filename = py_file.name
        docs_lines.append(f"## {filename}")
        docs_lines.append("")

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                class_doc = ast.get_docstring(node) or ""
                docs_lines.append(f"### {node.name}")
                if class_doc:
                    docs_lines.append(f"*{class_doc}*")
                else:
                    docs_lines.append("_No docstring_")
                docs_lines.append("")

                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        func_doc = ast.get_docstring(item) or ""
                        docs_lines.append(f"- **{item.name}(...)**")
                        if func_doc:
                            docs_lines.append(f"  *{func_doc}*")
                        else:
                            docs_lines.append("  _No docstring_")
                        docs_lines.append("")

            elif isinstance(node, ast.FunctionDef):
                func_doc = ast.get_docstring(node) or ""
                docs_lines.append(f"- **{node.name}(...)**")
                if func_doc:
                    docs_lines.append(f"  *{func_doc}*")
                else:
                    docs_lines.append("  _No docstring_")
                docs_lines.append("")

    return "\n".join(docs_lines)


GENERATE_DOCS = _text_output_tool(
    name="generate_docs",
    description=(
        "Generate documentation from Python docstrings and comments.\n\n"
        "Creates a markdown summary of all public functions and classes found\n"
        "in Python files under the given directory."
    ),
    parameters={
        "path": {"type": "string"},
    },
    execute=_generate_docs_execute,
    concurrency_safe=True,
)


# ---------------------------------------------------------------------------
# Add repo tool
# ---------------------------------------------------------------------------

def _add_repo_execute(args: dict[str, Any], _run_ctx: Any) -> str:
    from ..utils.home import find_home
    from ..utils.repo_map import parse_repo_map, resolve_repo

    ref = args["ref"]
    confirm = bool(args.get("confirm", False))

    home = find_home()
    if home is None:
        return "Error: no agents-home checkout is configured."
    entries = parse_repo_map((home / "AGENTS.md").read_text(encoding="utf-8"))
    entry = resolve_repo(entries, ref)
    if entry is None:
        return f"Error: '{ref}' is not in the home repo map."

    target = (home / entry.path).resolve()
    if target.is_dir():
        return f"Resolved '{entry.name}' to {target}."

    if not entry.clone_url:
        return f"Error: '{entry.name}' has no clone URL in the map."
    if not confirm:
        return (
            f"Confirm with confirm=true to clone '{entry.name}' from "
            f"{entry.clone_url} into {target}."
        )

    result = subprocess.run(
        ["git", "clone", entry.clone_url, str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"Error: clone failed: {result.stderr.strip()[:300]}"
    return f"Cloned '{entry.name}' into {target}."


ADD_REPO = _text_output_tool(
    name="add_repo",
    description=(
        "Resolve a repo name, clone URL or local directory from the home map."
    ),
    parameters={
        "ref": {"type": "string", "required": True},
        "confirm": {"type": "boolean"},
    },
    execute=_add_repo_execute,
)


# ---------------------------------------------------------------------------
# All tools
# ---------------------------------------------------------------------------

ALL_TOOLS: list[dict[str, Any]] = [
    ADD_REPO,
    READ_FILE,
    WRITE_FILE,
    EDIT_FILE,
    DELETE_FILE,
    LIST_DIRECTORY,
    LOAD_SKILL,
    GREP_FILES,
    RUN_COMMAND,
    VERIFY_REPO,
    WEB_SEARCH,
    RELOAD_MODULE,
    CODE_METRICS,
    FIND_DUPLICATES,
    GENERATE_DOCS,
]


def register_tools(ctx: Any) -> None:
    """Register all home-swe-home tools on an mth context."""
    for tool in ALL_TOOLS:
        ctx.tools.register(tool)