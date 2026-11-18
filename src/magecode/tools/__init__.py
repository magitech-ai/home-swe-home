"""magecode's tool services, built as anima components.

Public API: ``ToolService`` plus all individual tool Service classes.
Schema inference lives in ``magecode.utils.schema``. Each tool lives in its
own file under ``src/magecode/tools/`` with the filename matching the tool
name (e.g. ``read_file.py`` defines ``ReadFileService``).
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
from .code_metrics import CodeMetricsService
from .delete_file import DeleteFileService
from .edit_file import EditFileService
from .executor import ToolService  # noqa: F401
from .find_duplicates import FindDuplicatesService
from .generate_docs import GenerateDocsService
from .grep_files import GrepFilesService
from .list_directory import ListDirectoryService
from .read_file import ReadFileService
from .reload_module import ReloadModuleService
from .run_command import RunCommandService
from .web_search import WebSearchService
from .write_file import WriteFileService

# The services that are model-facing tools (used by CoreLoopService to build
# the tool schema list and by tests to enumerate tools).
TOOL_SERVICES = (
    ReadFileService,
    WriteFileService,
    EditFileService,
    DeleteFileService,
    ListDirectoryService,
    GrepFilesService,
    RunCommandService,
    WebSearchService,
    ReloadModuleService,
    CodeMetricsService,
    FindDuplicatesService,
    GenerateDocsService,
)
