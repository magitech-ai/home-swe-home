"""Tool registry: JSON schemas plus execution.

Tools run in the current working directory. This is a local, personal agent:
``run_command`` can run arbitrary programs, so use it with care.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

CHAT_COMPLETION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file and return its text contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of the file to read.",
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
            "description": "Create or overwrite a file with the given text.",
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
            "name": "list_directory",
            "description": "List the entries of a directory.",
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
            "description": "Search files for a regex pattern.",
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
            "description": "Run a shell command with a timeout and return its output.",
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
]


def tool_schemas() -> list[dict[str, Any]]:
    """Return the OpenAI-compatible tool schemas."""
    return CHAT_COMPLETION_TOOLS


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


_TOOLS: dict[str, Callable[..., str]] = {
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
    "grep_files": grep_files,
    "run_command": run_command,
}


def execute_tool(function_name: str, arguments_json: str) -> str:
    """Execute one tool call and return its result as text.

    Tool failures are caught and returned as error text so the model can react
    instead of the turn crashing.
    """
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as error:
        return f"Error: invalid tool arguments: {error}"
    func = _TOOLS.get(function_name)
    if func is None:
        return f"Error: unknown tool {function_name!r}"
    try:
        return func(**arguments)
    except Exception as error:  # report tool failure back to the model
        return f"Error: {type(error).__name__}: {error}"
