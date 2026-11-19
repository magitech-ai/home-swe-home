# 0001. Build magecode on the anima micro-kernel

Date: 2026-11-17
Status: accepted

## Context

magecode is a small coding agent: a turn loop that calls the NVIDIA API, runs
the tools the model requests, and feeds results back. It began with a plain
function-based core loop and `@tool`-decorated functions with a hand-rolled
registry (`_TOOLS`, `_TOOL_SCHEMAS`). The Magitech ecosystem already has a
component micro-kernel, anima, which magitech-harness and mth-plugins build
on. The component pattern is validated at scale by large agent harnesses.

A spike (`run_command` and `greeter` as anima Services) confirmed:
- Services mount on a `Context` and are accessible by name (`ctx.run_command`)
- `inject = ["run_command"]` gives automatic dependency ordering
- `await ctx.flush()` activates fibers deterministically
- `service_schema()` derives model-facing JSON schemas from `__call__`

## Decision

Build magecode on anima. Every capability is an anima `Service` mounted on a
`Context`:

- `CoreLoopService`, all 12 tool services, and the REPL/CLI entry points
- `context.py::build_context()` is the single assembly point (`TOOL_SERVICES`)
- `execute_tool()` looks up services on the Context rather than a private dict
- `service_schema()` replaces the `@tool` decorator's schema inference; the
  decorator and its registries were deleted
- CLI and REPL are async and bootstrap the Context
- Python requirement raised to 3.12+ (anima's floor); anima is a git dependency
  pinned in `uv.lock`

## Consequences

- Magecode is composable with the rest of the Magitech ecosystem and follows
  the same invariants as magitech-harness/mth-plugins.
- Tool wiring has two touch points (re-export in `tools/__init__.py`, entry in
  `context.py::TOOL_SERVICES`) instead of decorator side effects.
- Tests are async: mount services on a `Context`, `await ctx.flush()`, then
  call via `ctx.<service>`.
- The git dependency on anima means `uv sync` fetches from GitHub; the
  `uv.lock` pin keeps builds reproducible. Since Magitech controls anima,
  breaking API changes can be coordinated.
- Python 3.10/3.11 users must upgrade to 3.12+.
- Deferred: `reload_module` keeps its own mtime tracking rather than using
  anima's `HmrService` — the tool loads arbitrary files by path (via
  `spec_from_file_location`) and enforces read-before-edit, while `HmrService`
  is an async directory watcher that reloads already-imported modules. The
  one technique adopted from HMR is bytecode-cache invalidation (see the
  reload tool).
