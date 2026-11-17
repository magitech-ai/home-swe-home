# Agent Guidelines

## Magecode Architecture & Invariants

- **Repository Role**: `magecode` is a small coding agent: a mini Claude Code loop
  over the NVIDIA API. It sends a task to the model, runs the tools the model
  requests, feeds the results back, and repeats until the model stops asking.
- **Core Loop** (`src/magecode/core_loop.py`): non-streaming turn loop with
  `max_turns` (default 20). Model replies are appended verbatim; tool results
  are appended as `tool` messages. `Ctrl-C` raises `TurnInterrupted` and
  aborts the current turn only, not the program.
- **Tool Set** (`src/magecode/tools/`): 12 self-registering tools via the
  `@tool` decorator. `read_file` marks a path readable; `edit_file` and
  `reload_module` are refused for unread paths (read-before-edit rule tracked
  per turn via a `read_files` set). Every tool returns text — even failures —
  so the turn never crashes on a tool error.
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

1. Create `src/magecode/tools/<name>.py` with a single function decorated with
   `@tool`.
2. The decorator infers the JSON schema from the function signature and
   docstring (Google-style `Args:` section). Parameters named `read_files` are
   injected at call time and excluded from the schema.
3. The module is auto-registered via the import in `src/magecode/tools/__init__.py`.
4. Add unit tests under `tests/unit/test_tools.py`. Maintain 100% coverage.

## Magecode-Specific References

### Issue tracker
GitHub Issues via `gh` CLI (`magitech-ai` organization).

### Triage labels
Canonical five-role triage vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs
Single-context layout (`DESIGN.md` + `PLAN.md`).
