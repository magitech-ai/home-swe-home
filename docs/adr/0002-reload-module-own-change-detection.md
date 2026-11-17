# 0002. Keep reload_module's own change detection

Date: 2026-11-17
Status: accepted

## Context

`reload_module` is a tool that loads an arbitrary `.py` file by path via
`importlib.util.spec_from_file_location` and re-executes it under a caller-
chosen module name. It enforces read-before-edit (the path must be in the
per-turn `read_files` set) and reports whether a reload actually changed
anything.

anima ships `HmrService`, a hot-reload service. We investigated delegating
`reload_module` to it to avoid duplicating reload logic.

## Decision

Do **not** delegate to `HmrService`. Keep magecode's own mtime tracking in
`reload_module.py`. The two have different semantics:

- `HmrService.reload_module()` is async, watches directories, operates on
  modules already in `sys.modules`, and reloads via `importlib.reload`. It is
  designed for automatic, event-driven reload of mounted components.
- magecode's tool is a synchronous, model-invoked call that loads arbitrary
  files by path (including copies not in `sys.modules`) and enforces the
  read-before-edit contract.

Adopt one technique from anima's HMR source: track `(mtime, size)` and delete
cached bytecode before executing a module.

## Consequences

- `reload_module.py` keeps a small `_module_stats` dict and a few lines of
  stat/bytecode logic — a deliberate, documented duplication.
- Fixed a real bug: two same-size edits within the same second previously
  executed stale bytecode. A regression test writes a same-size change with
  an import-time side effect and asserts the new code ran.
- The async/sync boundary and arbitrary-path loading make future delegation
  to `HmrService` a larger redesign, not a drop-in swap.
