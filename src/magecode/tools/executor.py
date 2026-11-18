"""Tool execution Service: ``ctx.tools.execute()``.

Looks up a tool Service on the anima Context and calls it with parsed
arguments. ``read_files`` is injected into any tool that accepts it. Failures
are caught and returned as error text so the model can react.
"""

from __future__ import annotations

import inspect
import json
from typing import cast

from anima import Context, Service


class ToolService(Service):
    """The tool registry/execution pipeline mounted as ``ctx.tools``."""

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "tools")

    def execute(
        self,
        function_name: str,
        arguments_json: str,
        *,
        read_files: set[str] | None = None,
    ) -> str:
        """Execute one tool call and return its result as text."""
        try:
            arguments = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as error:
            return (
                f"Error: invalid tool arguments: {error}. "
                "Retry with valid JSON matching the tool's parameter schema."
            )

        service = self.ctx.reflect.get(function_name)
        if service is None:
            available = ", ".join(sorted(self.ctx.reflect.store))
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
