"""Tool execution: ``execute_tool()`` and module-reload mtime tracking."""

from __future__ import annotations

import inspect
import json

from .registry import _TOOLS

_module_mtimes: dict[str, float] = {}


def get_module_mtime(module_name: str) -> float | None:
    """Return the cached mtime for *module_name*, or ``None`` if never tracked."""
    return _module_mtimes.get(module_name)


def execute_tool(
    function_name: str,
    arguments_json: str,
    *,
    read_files: set[str] | None = None,
) -> str:
    """Execute one tool call and return its result as text.

    Failures are caught and returned as error text so the model can react.
    ``read_files`` is injected into any tool that accepts it as a parameter;
    tools use it to enforce read-before-edit preconditions.
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

    if "read_files" in inspect.signature(func).parameters:
        arguments["read_files"] = read_files

    try:
        return func(**arguments)
    except Exception as error:
        return (
            f"Error: {type(error).__name__}: {error}. "
            "See the tool manual above for correct inputs; fix and retry."
        )
