"""Context assembly for magecode.

Builds an anima Context with all tool services mounted. Shared by the CLI and
REPL so there is a single source of truth for which components make up an
agent session.
"""

from __future__ import annotations

from anima import Context

from .core_loop import CoreLoopService
from .tools import (
    CodeMetricsService,
    DeleteFileService,
    EditFileService,
    FindDuplicatesService,
    GenerateDocsService,
    GrepFilesService,
    ListDirectoryService,
    ReadFileService,
    ReloadModuleService,
    RunCommandService,
    WebSearchService,
    WriteFileService,
)

# All tool services, in dependency order (no deps between tools currently)
TOOL_SERVICES = [
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
    CoreLoopService,
]


async def build_context() -> Context:
    """Create an anima Context and mount all agent services."""
    ctx = Context()
    for service_cls in TOOL_SERVICES:
        ctx.use(service_cls)
    await ctx.flush()
    return ctx
