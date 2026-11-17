"""Tool registry: JSON schemas (manuals) plus execution.

Every schema's ``description`` is the tool manual the model reads before
calling the tool. Tools run in the current working directory. This is a local,
personal agent: ``run_command`` can run arbitrary programs, so use it with
care.

The turn loop tracks which files have been read (``read_files`` set).
``edit_file`` only works on paths that have been read via ``read_file``.
Every tool call returns text back to the model -- even failures -- and every
error message says what to try next.

Hot‑reload support:
  - ``reload_module`` lets you re‑import a Python module that lives on disk,
    picking up any changes made since the last import.
  - The harness tracks module file‑mtimes in ``_module_mtimes`` so that
    repeated calls without changes are cheap.
"""

from __future__ import annotations

import ast
import json
import os
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
        {
            "type": "function",
            "function": {
                "name": "reload_module",
                "description": (
                    "Hot‑reload a Python module from disk, picking up any changes "
                    "made since the last import.  The module file must be a valid "
                    ".py file importable by importlib.  If the file's mtime has\n"
                    "not changed since the last reload, the function reports that "
                    "no reload was performed.\n\n"
                    "Usage:\n"
                    "  1. `read_file` the module you want to modify.\n"
                    "  2. Edit it with `edit_file`.\n"
                    "  3. Call `reload_module` with the same module name and the\n"
                    "     file path.  The module's top‑level namespace will be "
                    "re‑executed from disk.\n\n"
                    "Note: only the module's own namespace is refreshed; other "
                    "parts of the harness that import from it will keep references\n"
                    "to the old objects unless they re‑import.\n"
                    "On error: check the module name and file path, retry.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_name": {
                            "type": "string",
                            "description": (
                                "Name to assign to the re-loaded module "
                                "(must be a valid Python identifier)."
                            ),
                        },
                        "file_path": {
                            "type": "string",
                            "description": (
                                "Absolute or relative path to the .py file "
                                "containing the module source."
                            ),
                        },
                    },
                    "required": ["module_name", "file_path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "code_metrics",
                "description": (
                    "Calculate code quality metrics for Python files in a "
                    "directory.\n"
                    "Returns lines of code, cyclomatic complexity estimates, "
                    "and other metrics.\n"
                    "Useful for tracking improvement over recursive turns.\n"
                    "Manual:\n"
                    "  - Provide a directory path (defaults to '.').\n"
                    "  - Returns summary statistics for all .py files found.\n"
                    "  - On error: check the directory path, retry.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory to analyze (defaults to '.').",
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
                "name": "find_duplicates",
                "description": (
                    "Find duplicate code blocks across Python files.\n"
                    "Uses simple line-based comparison to find "
                    "near-identical code sequences.\n"
                    "Returns file:line ranges that are duplicated.\n"
                    "Manual:\n"
                    "  - Provide a directory path (defaults to current directory).\n"
                    "  - min_lines minimum number of consecutive lines to "
                    "consider a duplicate.\n"
                    "  - Returns matching blocks with file paths and line numbers.\n"
                    "  - On error: check the directory path, retry.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Directory to search for duplicates (defaults to '.')."
                            ),
                        },
                        "min_lines": {
                            "type": "integer",
                            "description": (
                                "Minimum number of consecutive lines for a "
                                "duplicate block (defaults to 3)."
                            ),
                        },
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_docs",
                "description": (
                    "Generate documentation from Python docstrings and "
                    "comments.\n"
                    "Creates a markdown summary of all public functions and "
                    "classes found\n"
                    "in Python files under the given directory.\n"
                    "Manual:\n"
                    "  - Provide a directory path (defaults to '.').\n"
                    "  - Returns markdown documentation with signatures "
                    "and docstrings.\n"
                    "  - On error: check the directory path, retry.\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Directory to generate docs for (defaults to '.')."
                            ),
                        }
                    },
                    "required": ["path"],
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


def code_metrics(*, path: str = ".") -> str:
    """Calculate code quality metrics for Python files in a directory.

    Returns lines of code, cyclomatic complexity estimates, and other metrics.
    Useful for tracking improvement over recursive turns.

    Manual:
      - Provide a directory path (defaults to '.').
      - Returns summary statistics for all .py files found.
      - On error: check the directory path, retry.
    """
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

        # Count blank lines
        blank_lines += sum(1 for line in lines if line.strip() == "")

        # Count comment lines
        comment_lines += sum(1 for line in lines if line.strip().startswith("#"))

        # Count top-level functions and classes by indentation
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("class "):
                class_count += 1
            elif stripped.startswith("def ") and not line.startswith((" ", "\t")):
                function_count += 1
            elif stripped and not stripped.startswith("#"):
                if not line.startswith((" ", "\t")):
                    pass  # module-level code resets class context implicitly

        # Estimate cyclomatic complexity
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


def find_duplicates(*, path: str = "", min_lines: int = 3) -> str:
    """Find duplicate code blocks across Python files.

    Uses simple line-based comparison to find near-identical code sequences.
    Returns file:line ranges that are duplicated.

    Manual:
      - Provide a directory path (defaults to current directory).
      - min_lines minimum number of consecutive lines to consider a duplicate.
      - Returns matching blocks with file paths and line numbers.
      - On error: check the directory path, retry.
    """
    if not path:
        path = "."

    root = Path(path)
    py_files: list[Path] = list(root.rglob("*.py"))

    # Read all files, storing lines
    file_lines: dict[Path, list[str]] = {}
    for f in py_files:
        try:
            text = f.read_text(encoding="utf-8")
            file_lines[f] = text.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

    seen: dict[str, list[tuple[Path, int]]] = {}

    for f, lines in file_lines.items():
        # Generate contiguous blocks of exactly min_lines
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


def generate_docs(*, path: str = ".") -> str:
    """Generate documentation from Python docstrings and comments.

    Creates a markdown summary of all public functions and classes found
    in Python files under the given directory.

    Manual:
      - Provide a directory path (defaults to '.').
      - Returns markdown documentation with signatures and docstrings.
      - On error: check the directory path, retry.
    """
    root = Path(path)
    py_files = list(root.rglob("*.py"))

    docs_lines: list[str] = []
    docs_lines.append(f"# Auto-generated Documentation for {path}")
    docs_lines.append("")
    docs_lines.append("_Generated by mini-claude recursive improvement tools_")
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


# ---------------------------------------------------------------------------
# Hot‑reload support
# ---------------------------------------------------------------------------

# Mapping: module file path -> mtime (float) of the last import.
_module_mtimes: dict[str, float] = {}


def _reload_module(*, module_name: str, file_path: str) -> str:
    """Re‑import *module_name* from *file_path*, picking up on‑disk changes.

    The function uses importlib to re-execute the module's source file,
    thereby picking up any edits made outside the process.  Only the
    module's top‑level namespace is returned; any objects that were
    imported elsewhere keep references to the old objects unless the
    caller re‑assigns them.

    Returns
    -------
    str
        A short status message summarising the reload.
    """
    import importlib
    import importlib.util

    path = os.path.abspath(file_path)
    if not path.endswith(".py"):
        path = path + ".py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return f"Error: could not create spec for {path}."
    # Reset any prior mtime tracking so we always re‑load.
    _module_mtimes.pop(module_name, None)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _module_mtimes[module_name] = os.path.getmtime(path)

    # If reloading mini_claude.tools, update _TOOLS in place so the running
    # harness picks up new tool registrations without a restart.
    if module_name == "mini_claude.tools":
        module_tools = getattr(module, "_TOOLS", {})
        globals()["_TOOLS"].update(module_tools)
        globals()["execute_tool"] = getattr(module, "execute_tool", execute_tool)

    return (
        f"Reloaded module '{module_name}' from {path} "
        f"(mtime={_module_mtimes[module_name]:.1f})."
    )


def get_module_mtime(module_name: str) -> float | None:
    """Return the cached mtime for *module_name*, or ``None`` if never tracked."""
    return _module_mtimes.get(module_name)


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
    "reload_module": _reload_module,
    "code_metrics": code_metrics,
    "find_duplicates": find_duplicates,
    "generate_docs": generate_docs,
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
        if function_name == "reload_module":
            if read_files is None:
                return "Refused: reload_module requires a read_files tracker."
            module_name = str(arguments.get("module_name", ""))
            file_path = str(arguments.get("file_path", ""))
            if read_files is not None and file_path not in read_files:
                return (
                    f"Refused: '{file_path}' has not been read yet. "
                    f"Call read_file on '{file_path}' first, then retry reload_module."
                )
            # Optional optimisation: skip if mtime hasn't changed
            cached = _module_mtimes.get(module_name)
            if cached is not None:
                try:
                    current_mtime = os.path.getmtime(os.path.abspath(file_path))
                except OSError:
                    current_mtime = None
                if current_mtime is not None and current_mtime == cached:
                    return (
                        f"No changes detected for module '{module_name}' "
                        f"since last reload (mtime={cached:.1f})."
                    )
            return _reload_module(module_name=module_name, file_path=file_path)
        return func(**arguments)
    except Exception as error:  # report tool failure back to the model
        return (
            f"Error: {type(error).__name__}: {error}. "
            "See the tool manual above for correct inputs; fix and retry."
        )
