"""Tool execution: ``execute_tool()`` and module-reload mtime tracking."""

from __future__ import annotations

import inspect
import json
from typing import cast

from anima import Context

_module_mtimes: dict[str, float] = {}


def get_module_mtime(module_name: str) -> float | None:
    """Return the cached mtime for *module_name*, or ``None`` if never tracked."""
    return _module_mtimes.get(module_name)


def execute_tool(
    ctx: Context,
    function_name: str,
    arguments_json: str,
    *,
    read_files: set[str] | None = None,
) -> str:
    """Execute one tool call via an anima Context service.

    Looks up the tool service on the anima *context* and calls it with the
    parsed arguments. ``read_files`` is injected into any tool that accepts it
    as a parameter; tools use it to enforce read-before-edit preconditions.

    Failures are caught and returned as error text so the model can react.
    """
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as error:
        return (
            f"Error: invalid tool arguments: {error}. "
            "Retry with valid JSON matching the tool's parameter schema."
        )

    service = ctx.reflect.get(function_name)
    if service is None:
        available = ", ".join(sorted(ctx.reflect.store))
        return f"Error: unknown tool {function_name!r}. Use one of: {available}."

    if "read_files" in inspect.signature(service.__call__).parameters:
        arguments["read_files"] = read_files

    try:
        return cast(str, service(**arguments))
    except Exception as error:
        return (
            f"Error: {type(error).__name__}: {error}. "
            "See the tool manual above for correct inputs; fix and retry."
        )
