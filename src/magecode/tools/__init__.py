"""magecode's tool services, built as anima components.

Public API: ``service_schema()``, ``execute_tool()``, plus all individual
tool Service classes. Individual tools live in their own files under
``src/magecode/tools/`` with the filename matching the tool name
(e.g. ``read_file.py`` defines ``ReadFileService``).
"""

from __future__ import annotations

# Import every tool service module so its Service class is available.
from . import (
    code_metrics,  # noqa: F401
    delete_file,  # noqa: F401
    edit_file,  # noqa: F401
    find_duplicates,  # noqa: F401
    generate_docs,  # noqa: F401
    grep_files,  # noqa: F401
    list_directory,  # noqa: F401
    read_file,  # noqa: F401
    reload_module,  # noqa: F401
    run_command,  # noqa: F401
    web_search,  # noqa: F401
    write_file,  # noqa: F401
)

# Re-export individual tool service classes for direct use.
from .code_metrics import CodeMetricsService  # noqa: F401
from .delete_file import DeleteFileService  # noqa: F401
from .edit_file import EditFileService  # noqa: F401
from .executor import execute_tool, get_module_mtime  # noqa: F401
from .find_duplicates import FindDuplicatesService  # noqa: F401
from .generate_docs import GenerateDocsService  # noqa: F401
from .grep_files import GrepFilesService  # noqa: F401
from .list_directory import ListDirectoryService  # noqa: F401
from .read_file import ReadFileService  # noqa: F401
from .registry import service_schema  # noqa: F401
from .reload_module import ReloadModuleService  # noqa: F401
from .run_command import RunCommandService  # noqa: F401
from .web_search import WebSearchService  # noqa: F401
from .write_file import WriteFileService  # noqa: F401
