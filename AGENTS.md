# Agent Guidelines

## Magecode Architecture & Invariants

- **Repository Role**: `magecode` is a small coding agent built on **anima**,
  Magitech's Python micro-kernel. It follows "everything is a component":
  every capability is an anima `Service` mounted on a `Context`.
  The agent sends a task to the model, runs the tools
  the model requests, feeds the results back, and repeats until the model
  stops asking.
- **Component Model**: `src/magecode/context.py` builds the session `Context`
  and mounts every capability as an anima Service (`AGENT_SERVICES`): the model
  adapter (`ctx.client`), system instructions (`ctx.instructions`), tool
  execution (`ctx.tools`), sandbox (`ctx.sandbox`), the core loop
  (`ctx.core_loop`), and all 15 tools. Services are accessed by name on the
  Context; no capability is called as a bare module function. Pure helpers
  live in `src/magecode/utils/` (`schema.py`, `text.py`, `harness.py`); config
  validation and the CLI/REPL entry points are the deliberate exceptions.
- **Editable Harness** (`src/magecode/harness/`): data, not code. `systemprompt.md`
  is the base system prompt (read by `InstructionsService.build()`);
  `tool_guidance.md` holds optional `## <tool_name>` sections appended to each
  tool's model-facing description by `service_schema()`. `MAGECODE_HARNESS_DIR`
  points an outer improvement loop at a candidate copy. Loaders are pure
  helpers in `utils/harness.py`; edits must not change behavior unless intended.
- **Core Loop** (`src/magecode/core_loop.py`): `CoreLoopService`, a non-streaming
  turn loop with `max_turns` (default 20). Model replies are appended verbatim;
  tool results are appended as `tool` messages. `Ctrl-C` raises
  `TurnInterrupted` and aborts the current turn only, not the program. Tool
  schemas are derived from each Service's `__call__` signature/docstring via
  `service_schema()`, plus editable `## <tool_name>` sections from
  `harness/tool_guidance.md`.
- **Tool Set** (`src/magecode/tools/`): 12 anima `Service` components.
  `ctx.tools.execute()` looks up a tool service on the Context and calls it.
  `read_file` marks a path readable; `edit_file` and `reload_module` are refused
  for unread paths (read-before-edit rule tracked per turn via a `read_files`
  set that `ctx.tools.execute` injects). Every tool returns text — even
  failures — so the turn never crashes on a tool error.
- **API Key** (`src/magecode/client.py`): `NVIDIA_API_KEY` from the environment
  only (`.env` fallback via python-dotenv, env var takes precedence). The key
  is never printed and never persisted. Missing key → clear message, exit 2.
- **Shell commands** (`src/magecode/tools/run_command.py`): `run_command` executes
  shell commands directly on the host by default (unsandboxed). The user is
  present, sees every command, and can abort any turn with Ctrl-C. Set
  `MAGECODE_SANDBOX=1` in the environment or pass `--sandbox` on the CLI to
  execute inside a fresh, throwaway Docker container with `--network none`,
  `--read-only` root FS, non-root user (current host UID:GID), `--cap-drop ALL`,
  `no-new-privileges`, CPU/memory/pids limits, `ulimit nofile/fsize`, and
  `--rm` ephemeral lifetime. The `workdir` is validated to be within the CWD
  tree so the sandbox can never mount `/etc`, `/`, or other sensitive host
  paths. The current directory is mounted as `/workspace` (read-write) so
  commands can operate on project files. Output is capped at 8 KB per stream
  in sandbox mode.

  **Security note:** unsandboxed commands run with the user's privileges,
  including access to environment variables such as `NVIDIA_API_KEY`. Use
  sandbox mode for untrusted model-generated commands.
- **Modes**: Interactive REPL by default (`> ` / `< ` prompts, `/model`,
  `/context`); headless with `-p "task"` (raw output, `[context: N tokens]`
  per call). `--model` overrides the default model.
- **Error Contract**: Missing key → exit 2. Bad model / API error / network
  failure → clear message, no traceback (headless exits 1; REPL reports and
  continues). Tool failures return `Error:` or `Refused:` text plus a "what to
  try next" hint.

## Shared Development Guidance

Follow the shared development guidance in [agents-home AGENTS](../agents-home/AGENTS.md).

- **Package manager**: `uv`. Use `uv sync` to install, `uv add <dep>` to add
  dependencies, `uv run --locked <tool>` for pinned tools.
- **Linting**: `uvx ruff check` and `uvx ruff format` (line length 88, select
  E/F/I).
- **Type-checking**: `uv run --locked mypy src` (strict: `disallow_untyped_defs`,
  `warn_return_any`, `warn_unused_configs`). `py.typed` is maintained.
- **Testing**: `uv run --locked pytest --cov=src/magecode --cov-fail-under=100`.
  100% statement + branch coverage required. Flat unit tests under
  `tests/unit/` with no `__init__.py`. No real API calls in tests.

## Adding a New Tool

1. Create `src/magecode/tools/<name>.py` with a `Service` subclass whose
   `__init__` calls `super().__init__(ctx, "<name>")` and whose `__call__` does
   the work. Parameters are keyword-only; `read_files` is injected at call time.
2. `service_schema()` infers the JSON schema from `__call__` (signature types
   and the class docstring's Google-style `Args:` section); `self`/`cls`/
   `read_files` are excluded.
3. Import and re-export the class in `src/magecode/tools/__init__.py`, and add
   it to `TOOL_SERVICES` in `src/magecode/context.py`.
4. Add unit tests under `tests/unit/test_tools.py`. Maintain 100% coverage.
   Tests mount services on a `Context` and `await ctx.flush()` before calling.

## Magecode-Specific References

### Issue tracker
GitHub Issues via `gh` CLI (`magitech-ai` organization).

### Triage labels
Canonical five-role triage vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs
Single-context layout (`DESIGN.md` + `docs/adr/`).
