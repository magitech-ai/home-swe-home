"""Tool registry: JSON schemas (manuals) plus execution.

Every schema's ``description`` is the tool manual the model reads before
calling the tool. Tools run in the current working directory. This is a local,
personal agent: ``run_command`` can run arbitrary programs, so use it with
care.

The turn loop tracks which files have been read (``read_files`` set).
``edit_file`` only works on paths that have been read via ``read_file``.
Every tool call returns text back to the model -- even failures -- and every
error message says what to try next.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


def tool_schemas() -> list[dict[str, Any]]:
    """Return the OpenAI-compatible tool schemas.

    Each schema's ``description`` is the tool manual the model reads.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": (
                    "Read a file and return its text contents. "
                    "Reading a file marks it as readable, which is required "
                    "before calling edit_file on that path.\n"
                    "Manual:\n"
                    "  - Provide the exact path of the file to read.\n"
                    "  - Returns the full file text (large files may be truncated).\n"
                    "  - After a successful read, the path is marked readable.\n"
                    "  - On error the result starts with 'Error:'; fix the path or\n"
                    "    permissions and call read_file again.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Exact path of the file to read.",
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": (
                    "Create or overwrite a file with the given text. "
                    "After writing, the path is marked readable so it can be "
                    "edited with edit_file.\n"
                    "Manual:\n"
                    "  - Provide the exact path and the full text content.\n"
                    "  - This overwrites any existing file at that path.\n"
                    "  - On error the result starts with 'Error:'; check the path\n"
                    "    and directory permissions, then call write_file again.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path of the file to write.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Text to write into the file.",
                        },
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": (
                    "Replace exact text in a file you have already read. "
                    "Replaces the first occurrence of old_string with "
                    "new_string.\n"
                    "Manual:\n"
                    "  - You must have called read_file on this path first;\n"
                    "    otherwise this tool is refused.\n"
                    "  - old_string must match the file text exactly (including\n"
                    "    whitespace and indentation).\n"
                    "  - Only the first occurrence is replaced.\n"
                    "  - If old_string is not found, the error says so; re-read\n"
                    "    the file to see the exact text, then retry.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path of a previously read file to edit.",
                        },
                        "old_string": {
                            "type": "string",
                            "description": "Exact text to replace.",
                        },
                        "new_string": {
                            "type": "string",
                            "description": "Text to replace old_string with.",
                        },
                    },
                    "required": ["path", "old_string", "new_string"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_file",
                "description": (
                    "Delete a file. Only files that exist can be deleted.\n"
                    "Manual:\n"
                    "  - Provide the exact path of the file to delete.\n"
                    "  - Returns confirmation naming the deleted file.\n"
                    "  - On error the result starts with 'Error:'; check the path\n"
                    "    and try again.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Exact path of the file to delete.",
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": (
                    "List the entries of a directory. Use this to verify what "
                    "files exist after writing or deleting.\n"
                    "Manual:\n"
                    "  - Provide a directory path (defaults to '.').\n"
                    "  - Returns one entry per line; directories end with '/'.\n"
                    "  - On error the result starts with 'Error:'.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory to list (defaults to '.').",
                        }
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "grep_files",
                "description": (
                    "Search files for a regex pattern. Returns matching lines "
                    "with file:line:content, capped at 50 matches.\n"
                    "Manual:\n"
                    "  - Provide a regular expression pattern.\n"
                    "  - Optionally provide a directory to search (defaults to '.').\n"
                    "  - Binary and unreadable files are skipped.\n"
                    "  - Returns 'No matches.' if nothing is found.\n"
                    "  - On error the result starts with 'Error:'; check the path\n"
                    "    and try again.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Regular expression to search for.",
                        },
                        "path": {
                            "type": "string",
                            "description": "Directory to search (defaults to '.').",
                        },
                    },
                    "required": ["pattern"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": (
                    "Run a shell command with a timeout and return its output. "
                    "This runs arbitrary programs in the current directory.\n"
                    "Manual:\n"
                    "  - Provide the command line as a single string.\n"
                    "  - Optionally provide a timeout in seconds (default 30).\n"
                    "  - Returns stdout, stderr, and exit code.\n"
                    "  - On timeout or failure the result starts with 'Error:'.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Command line to run.",
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Timeout in seconds (default 30).",
                        },
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Search the web using DuckDuckGo (no API key required). "
                    "Returns result titles and URLs.\n"
                    "Manual:\n"
                    "  - Provide a search query string.\n"
                    "  - Returns up to 8 results as 'title: url' lines.\n"
                    "  - Returns 'No web results found.' if nothing matches.\n"
                    "  - On network failure the result starts with 'Error:';\n"
                    "    check your connection and retry the query.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string.",
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
    ]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def read_file(*, path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_file(*, path: str, content: str) -> str:
    Path(path).write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}."


def list_directory(*, path: str = ".") -> str:
    entries = sorted(Path(path).iterdir())
    lines: list[str] = []
    for entry in entries:
        lines.append(f"{entry.name}/" if entry.is_dir() else entry.name)
    return "\n".join(lines) if lines else "(empty)"


def grep_files(*, pattern: str, path: str = ".") -> str:
    regex = re.compile(pattern)
    root = Path(path)
    matches: list[str] = []
    for file in root.rglob("*"):
        if not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # skip binaries and unreadable files
        for line_number, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{file}:{line_number}: {line}")
                if len(matches) >= 50:
                    break
        if len(matches) >= 50:
            break
    return "\n".join(matches) if matches else "No matches."


def run_command(*, command: str, timeout: float | int = 30) -> str:
    completed = subprocess.run(
        shlex.split(command),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    parts: list[str] = []
    if completed.stdout:
        parts.append(f"stdout:\n{completed.stdout}")
    if completed.stderr:
        parts.append(f"stderr:\n{completed.stderr}")
    parts.append(f"exit code: {completed.returncode}")
    return "\n".join(parts)


def web_search(*, query: str) -> str:
    """Search the web via DuckDuckGo HTML (no API key)."""
    encoded = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{encoded}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as error:
        return (
            f"Error: web search failed: {error}. "
            "Check your network connection and retry the query."
        )

    results: list[str] = []
    for match in re.finditer(
        r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>',
        html,
        re.DOTALL,
    ):
        href = match.group(1)
        title = re.sub(r"<.*?>", "", match.group(2)).strip()
        if title and href:
            results.append(f"{title}: {href}")
        if len(results) >= 8:
            break

    if not results:
        return "No web results found. Try rephrasing the query."
    return "\n".join(results)


def _edit_file(*, path: str, old_string: str, new_string: str) -> str:
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


def _delete_file(*, path: str) -> str:
    target = Path(path)
    target.unlink()
    return f"Deleted {path}."


_TOOLS: dict[str, Callable[..., str]] = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": _edit_file,
    "delete_file": _delete_file,
    "list_directory": list_directory,
    "grep_files": grep_files,
    "run_command": run_command,
    "web_search": web_search,
}


def execute_tool(
    function_name: str,
    arguments_json: str,
    *,
    read_files: set[str] | None = None,
) -> str:
    """Execute one tool call and return its result as text.

    Tool failures are caught and returned as error text so the model can react
    instead of the turn crashing. ``read_files`` tracks which paths the model
    has read; ``edit_file`` is refused for unread paths.
    """
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as error:
        return (
            f"Error: invalid tool arguments: {error}. "
            "Retry with valid JSON matching the tool's parameter schema."
        )

    func = _TOOLS.get(function_name)
    if func is None:
        return (
            f"Error: unknown tool {function_name!r}. "
            f"Use one of: {', '.join(sorted(_TOOLS))}."
        )

    try:
        if function_name == "read_file":
            result = func(**arguments)
            if read_files is not None:
                read_files.add(str(arguments.get("path", "")))
            return result
        if function_name == "write_file":
            result = func(**arguments)
            if read_files is not None:
                read_files.add(str(arguments.get("path", "")))
            return result
        if function_name == "edit_file":
            path = str(arguments.get("path", ""))
            if read_files is None or path not in read_files:
                return (
                    f"Refused: '{path}' has not been read yet. "
                    f"Call read_file on '{path}' first, then retry edit_file."
                )
            return func(**arguments)
        return func(**arguments)
    except Exception as error:  # report tool failure back to the model
        return (
            f"Error: {type(error).__name__}: {error}. "
            "See the tool manual above for correct inputs; fix and retry."
        )
