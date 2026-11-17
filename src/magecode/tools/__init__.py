"""Tool registry: JSON schemas (instructions) plus execution.

Every tool is defined as a Python function decorated with ``@tool``.  The
decorator infers the tool schema from the function itself:

* ``func.__name__`` becomes the tool name
* ``func.__doc__`` becomes the tool instructions (first paragraph = description,
  ``Args:`` section = parameter descriptions)
* ``inspect.signature(func)`` provides parameter names, types, and which are
  required (no default value)

This follows the Google ADK convention: no redundant instructions or parameters
arguments needed on the decorator.
"""

from __future__ import annotations

import inspect
import json
import os
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_TOOLS: dict[str, Callable[..., str]] = {}
_TOOL_SCHEMAS: list[dict[str, Any]] = []
_module_mtimes: dict[str, float] = {}

_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _python_type_to_json_schema_type(annotation: Any) -> str:
    """Map a Python type annotation to a JSON Schema type string."""
    if annotation is inspect.Parameter.empty:
        return "string"  # safest default
    if annotation in _TYPE_MAP:
        return _TYPE_MAP[annotation]
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        # Handle Optional[X] -> X, Union[str, None] -> str, etc.
        args = getattr(annotation, "__args__", ())
        for arg in args:
            if arg is not type(None):
                return _python_type_to_json_schema_type(arg)
    return "string"


def _parse_docstring(doc: str | None) -> tuple[str, dict[str, str]]:
    """Parse a docstring into (description, param_descriptions).

    Supports Google-style docstrings, e.g.:

        Do something useful.

        Args:
            path: The file path to read.
            timeout: Seconds before giving up.

    If there is no ``Args:`` section, all parameter descriptions are empty.
    """
    if not doc:
        return "", {}

    lines = doc.strip().splitlines()
    description_lines: list[str] = []
    param_descriptions: dict[str, str] = {}
    in_args = False

    for line in lines:
        stripped = line.strip()
        if stripped == "Args:" or stripped == "Arguments:":
            in_args = True
            continue
        if in_args:
            # Args section ends at a blank line or a new section header
            if not stripped:
                break
            if ":" in stripped:
                name, _, desc = stripped.partition(":")
                param_descriptions[name.strip()] = desc.strip()
        elif stripped:
            description_lines.append(stripped)

    return " ".join(description_lines), param_descriptions


def tool(
    func: Callable[..., str] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> Callable[..., str] | Callable[[Callable[..., str]], Callable[..., str]]:
    """Register a Python function as an agent tool.

    The decorator infers everything from the function itself:

    * ``func.__name__`` -> tool name
    * ``func.__doc__`` -> tool instructions (description + Args section)
    * ``inspect.signature(func)`` -> parameter names, types, requiredness

    All inferred values can be overridden by passing arguments to the
    decorator::

        @tool(name="custom_name")
        def read_file(*, path: str) -> str:
            \"\"\"Read a file's text contents.

            Args:
                path: Exact path of the file to read.
            \"\"\"
            ...

    Usage::

        @tool
        def read_file(*, path: str) -> str:
            ...

    Parameters
    ----------
    name:
        Override the tool name (defaults to the function name).
    description:
        Override the tool instructions (defaults to the function docstring).
    parameters:
        Override the JSON Schema parameters (defaults to inference from the
        function signature).
    """

    def decorator(f: Callable[..., str]) -> Callable[..., str]:
        sig = inspect.signature(f)
        tool_name = name or f.__name__

        doc_description, param_descs = _parse_docstring(f.__doc__)

        if description is None:
            tool_description = doc_description
        else:
            tool_description = description

        if parameters is not None:
            param_schema = parameters
        else:
            properties: dict[str, Any] = {}
            required: list[str] = []

            for param_name, param in sig.parameters.items():
                if param_name == "self" or param_name == "cls":
                    continue
                param_type = _python_type_to_json_schema_type(param.annotation)
                properties[param_name] = {
                    "type": param_type,
                    "description": param_descs.get(param_name, ""),
                }
                if param.default is inspect.Parameter.empty:
                    required.append(param_name)

            param_schema = {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            }

        schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_description,
                "parameters": param_schema,
            },
        }

        _TOOLS[tool_name] = f
        # Idempotent: replace an existing schema with the same name so that
        # hot-reloading a tool module doesn't append duplicates.
        for idx, existing in enumerate(_TOOL_SCHEMAS):
            if existing["function"]["name"] == tool_name:
                _TOOL_SCHEMAS[idx] = schema
                break
        else:
            _TOOL_SCHEMAS.append(schema)
        return f

    # Allow both @tool and @tool()
    if func is not None:
        return decorator(func)
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
from .reload_module import reload_module as _reload_module_fn  # noqa: E402,F401  (side effects: @tool registration)
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
            # Lazy import to avoid module/function name collision
            import importlib

            _reload_mod = importlib.import_module(".reload_module", "magecode.tools")
            _reload_module_fn: Callable[..., str] = _reload_mod.reload_module

            return _reload_module_fn(module_name=module_name, file_path=file_path)
        return func(**arguments)
    except Exception as error:  # report tool failure back to the model
        return (
            f"Error: {type(error).__name__}: {error}. "
            "See the tool manual above for correct inputs; fix and retry."
        )


def get_module_mtime(module_name: str) -> float | None:
    """Return the cached mtime for *module_name*, or ``None`` if never tracked."""
    return _module_mtimes.get(module_name)
