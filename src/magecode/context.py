"""Context assembly for magecode.

Builds an anima Context with all agent services mounted. Shared by the CLI and
REPL so there is a single source of truth for which components make up an
agent session. Every capability — model adapter, instructions, tool execution,
sandbox, core loop, and each tool — is a Service here.
"""

from __future__ import annotations

from anima import Context

from .client import ClientService
from .core_loop import CoreLoopService
from .instructions import InstructionsService
from .sandbox import SandboxService
from .skills import SkillsService
from .tools import (
    CodeMetricsService,
    DeleteFileService,
    EditFileService,
    FindDuplicatesService,
    GenerateDocsService,
    GrepFilesService,
    ListDirectoryService,
    LoadSkillService,
    ReadFileService,
    ReloadModuleService,
    RunCommandService,
    WebSearchService,
    WriteFileService,
)
from .tools.executor import ToolService

# All agent services, in dependency order (no deps between tools currently)
AGENT_SERVICES = [
    ClientService,
    InstructionsService,
    ToolService,
    SandboxService,
    SkillsService,
    ReadFileService,
    WriteFileService,
    EditFileService,
    DeleteFileService,
    ListDirectoryService,
    LoadSkillService,
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
    for service_cls in AGENT_SERVICES:
        ctx.use(service_cls)
    await ctx.flush()
    return ctx
