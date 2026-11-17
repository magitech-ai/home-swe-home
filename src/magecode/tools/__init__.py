"""Tool registry and execution.

Public API: ``tool()``, ``tool_schemas()``, ``execute_tool()``, plus all
individual tool functions. Individual tools live in their own files under
``src/magecode/tools/`` with the filename matching the tool name.
"""

from __future__ import annotations

# Import every tool module so its ``@tool`` decorator registers side effects.
from .code_metrics import code_metrics  # noqa: F401
from .delete_file import delete_file  # noqa: F401
from .edit_file import edit_file  # noqa: F401
from .executor import execute_tool, get_module_mtime  # noqa: F401  (re-exported public API)
from .find_duplicates import find_duplicates  # noqa: F401
from .generate_docs import generate_docs  # noqa: F401
from .grep_files import grep_files  # noqa: F401
from .list_directory import list_directory  # noqa: F401
from .read_file import read_file  # noqa: F401
from .registry import (  # noqa: F401  (re-exported public API)
    _TOOLS,
    _parse_docstring,
    _python_type_to_json_schema_type,
    tool,
    tool_schemas,
)
from .reload_module import reload_module  # noqa: F401
from .run_command import run_command  # noqa: F401
from .web_search import web_search  # noqa: F401
from .write_file import write_file  # noqa: F401
