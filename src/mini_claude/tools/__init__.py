"""Tool registry: JSON schemas (manuals) plus execution.

Every schema's ``description`` is the tool manual the model reads before
calling the tool. Tools run in the current working directory. This is a local,
personal agent: ``run_command`` can run arbitrary programs, so use it with
care.

The turn loop tracks which files have been read (``read_files`` set).
``edit_file`` and ``reload_module`` only work on paths read via ``read_file``.
Every tool call returns text back to the model -- even failures -- and every
error message says what to try next.

Hot‑reload support:
  - ``reload_module`` lets you re‑import a Python module that lives on disk,
    picking up any changes made since the last import.
  - The harness tracks module file‑mtimes in ``_module_mtimes`` so that
    repeated calls without changes are cheap.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_TOOLS: dict[str, Callable[..., str]] = {}
_TOOL_SCHEMAS: list[dict[str, Any]] = []
_module_mtimes: dict[str, float] = {}


def tool(
    *,
    name: str | None = None,
    manual: str,
    parameters: dict[str, Any] | None = None,
) -> Callable[[Callable[..., str]], Callable[..., str]]:
    """Register a Python function as an agent tool.

    The decorated function is automatically added to both ``_TOOLS``
    (execution) and ``_TOOL_SCHEMAS`` (schema).  ``tool_schemas()`` returns
    the accumulated schemas.

    Parameters
    ----------
    name:
        Override the tool name (defaults to the function name).
    manual:
        The tool manual the model reads.  Required.
    parameters:
        OpenAI-compatible JSON Schema for the tool's parameters.  Defaults to
        an empty object schema.
    """

    def decorator(func: Callable[..., str]) -> Callable[..., str]:
        tool_name = name or func.__name__
        _TOOLS[tool_name] = func
        schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": manual or func.__doc__ or "",
                "parameters": parameters
                or {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        # Idempotent: replace an existing schema with the same name so that
        # hot-reloading a tool module doesn't append duplicates.
        for idx, existing in enumerate(_TOOL_SCHEMAS):
            if existing["function"]["name"] == tool_name:
                _TOOL_SCHEMAS[idx] = schema
                break
        else:
            _TOOL_SCHEMAS.append(schema)
        return func

    return decorator


def tool_schemas() -> list[dict[str, Any]]:
    """Return the OpenAI-compatible tool schemas.

    Each schema's ``description`` is the tool manual the model reads.
    """
    return list(_TOOL_SCHEMAS)


# ---------------------------------------------------------------------------
# Tool implementations (auto-registered via @tool decorator in each submodule)
# ---------------------------------------------------------------------------

from .code_metrics import code_metrics  # noqa: E402,F401  (side effects: @tool registration)
from .delete_file import delete_file  # noqa: E402,F401  (side effects: @tool registration)
from .edit_file import edit_file  # noqa: E402,F401  (side effects: @tool registration)
from .find_duplicates import find_duplicates  # noqa: E402,F401  (side effects: @tool registration)
from .generate_docs import generate_docs  # noqa: E402,F401  (side effects: @tool registration)
from .grep_files import grep_files  # noqa: E402,F401  (side effects: @tool registration)
from .list_directory import list_directory  # noqa: E402,F401  (side effects: @tool registration)
from .read_file import read_file  # noqa: E402,F401  (side effects: @tool registration)
from .reload_module import reload_module  # noqa: E402,F401  (side effects: @tool registration)
from .run_command import run_command  # noqa: E402,F401  (side effects: @tool registration)
from .web_search import web_search  # noqa: E402,F401  (side effects: @tool registration)
from .write_file import write_file  # noqa: E402,F401  (side effects: @tool registration)


def execute_tool(
    function_name: str,
    arguments_json: str,
    *,
    read_files: set[str] | None = None,
) -> str:
    """Execute one tool call and return its result as text.

    Tool failures are caught and returned as error text so the model can react
    instead of the turn crashing. ``read_files`` tracks which paths the model
    has read; ``edit_file`` and ``reload_module`` are refused for unread paths.
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
            return reload_module(module_name=module_name, file_path=file_path)
        return func(**arguments)
    except Exception as error:  # report tool failure back to the model
        return (
            f"Error: {type(error).__name__}: {error}. "
            "See the tool manual above for correct inputs; fix and retry."
        )


def get_module_mtime(module_name: str) -> float | None:
    """Return the cached mtime for *module_name*, or ``None`` if never tracked."""
    return _module_mtimes.get(module_name)
