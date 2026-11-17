"""Tool registry: ``@tool`` decorator and JSON-schema inference."""

from __future__ import annotations

import inspect
from typing import Any, Callable

_TOOLS: dict[str, Callable[..., str]] = {}
_TOOL_SCHEMAS: list[dict[str, Any]] = []

_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _python_type_to_json_schema_type(annotation: Any) -> str:
    """Map a Python type annotation to a JSON Schema type string."""
    if annotation is inspect.Parameter.empty:
        return "string"
    if annotation in _TYPE_MAP:
        return _TYPE_MAP[annotation]
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        for arg in getattr(annotation, "__args__", ()):
            if arg is not type(None):
                return _python_type_to_json_schema_type(arg)
    return "string"


def _parse_docstring(doc: str | None) -> tuple[str, dict[str, str]]:
    """Parse a docstring into (description, param_descriptions).

    Supports Google-style docstrings with an optional ``Args:`` section.
    """
    if not doc:
        return "", {}
    lines = doc.strip().splitlines()
    description_lines: list[str] = []
    param_descriptions: dict[str, str] = {}
    in_args = False
    for line in lines:
        stripped = line.strip()
        if stripped in ("Args:", "Arguments:"):
            in_args = True
            continue
        if in_args:
            if not stripped:
                break  # blank line ends Args section
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

    Infers name, description, and parameters from the function itself
    (docstring summary, ``Args:`` section, signature annotations).
    All values can be overridden via decorator arguments.
    """

    def decorator(f: Callable[..., str]) -> Callable[..., str]:
        sig = inspect.signature(f)
        tool_name = name or f.__name__

        doc_description, param_descs = _parse_docstring(f.__doc__)
        tool_description = description or doc_description

        if parameters is not None:
            param_schema = parameters
        else:
            properties: dict[str, Any] = {}
            required: list[str] = []
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls", "read_files"):
                    continue  # injected at call time, not part of the schema
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
        for idx, existing in enumerate(_TOOL_SCHEMAS):
            if existing["function"]["name"] == tool_name:
                _TOOL_SCHEMAS[idx] = schema
                break
        else:
            _TOOL_SCHEMAS.append(schema)
        return f

    if func is not None:
        return decorator(func)
    return decorator


def tool_schemas() -> list[dict[str, Any]]:
    """Return the OpenAI-compatible tool schemas."""
    return list(_TOOL_SCHEMAS)
