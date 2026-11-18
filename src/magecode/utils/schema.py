"""JSON-schema inference for magecode's anima Service tools.

``service_schema()`` inspects a Service class's ``__call__`` method and builds
an OpenAI-compatible tool schema (description from the class docstring,
parameters from the signature, types from annotations). Pure helpers — no
Service, no state.
"""

from __future__ import annotations

import inspect
from typing import Any

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


def service_schema(service_cls: type, name: str | None = None) -> dict[str, Any]:
    """Build a JSON schema from a Service class's ``__call__`` method.

    Description comes from the class docstring, parameters from the
    ``__call__`` signature (skipping ``self``, ``cls``, ``read_files`` which
    are injected at call time), types from annotations.

    Args:
        service_cls: The Service class to build a schema from.
        name: Override the tool name (defaults to the class name with
            ``Service`` suffix stripped).
    """
    sig = inspect.signature(service_cls.__call__)

    if name is None:
        class_name = service_cls.__name__
        if class_name.endswith("Service"):
            tool_name = class_name[: -len("Service")]
        else:
            tool_name = class_name
    else:
        tool_name = name

    doc_description, param_descs = _parse_docstring(service_cls.__doc__)

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

    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": doc_description,
            "parameters": param_schema,
        },
    }
