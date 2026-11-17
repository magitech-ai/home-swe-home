# Design doc — magecode

A small coding agent in Python: a mini Claude Code. Core loop — send the task to
the model, run the tools the model asks for, send the results back, and repeat
until the model stops asking. Model replies are printed exactly as they came
back.

## How to run

```sh
# From this repo root
uv sync                      # install deps + this package
export NVIDIA_API_KEY=nvapi-...   # see "API key setup" below; never echo this

# Headless: one task, nobody watching (requires your key)
uv run magecode -p "say hi in three words"

# Interactive chat (default)
uv run magecode

# Pick a model
uv run magecode --model nvidia/nemotron-3.5-lightning-30b-a3b -p "..."
```

Inside chat, `/model meta/llama-3.1-8b-instruct` switches models for the rest of
the session. Ctrl-C aborts the current turn only.

## API key setup

1. Sign in at https://build.nvidia.com and create an API key (starts with
   `nvapi-`).
2. Provide it via one of these, in priority order:

   - **Exported environment variable** (highest priority, best for CI):

     ```sh
     export NVIDIA_API_KEY=nvapi-...
     ```

   - **`.env` file** (fallback, best for local dev). Copy the template and
     fill in your key. `.env` is gitignored and never committed:

     ```sh
     cp .env.example .env
     # edit .env and add your key
     ```

   The program uses `python-dotenv` to load `.env`. Existing environment
   variables take precedence over `.env` values, so the fallback chain is:

   `exported NVIDIA_API_KEY` → `.env` → clear error message, exit 2

   Do not echo the key, do not commit it, and do not share it.
   This project reads `NVIDIA_API_KEY` from the environment.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Foundation | **anima** micro-kernel (Magitech's Python implementation of Cordis) | "Everything is a component": every capability is an anima Service on a Context. Matches the ecosystem (magitech-harness, mth-plugins) and the pattern validated by deepseek-harness (282k stars). You control anima, so API changes are coordinateable. |
| Language / runtime | Python 3.12+, `uv`-managed | anima requires 3.12+. Shared Magitech standards; strict mypy, ruff (line length 88), pytest |
| API | NVIDIA build.nvidia.com, OpenAI-compatible, `https://integrate.api.nvidia.com/v1` | User's Nvidia API key; the `openai` Python client speaks this protocol natively |
| Auth | `NVIDIA_API_KEY` environment variable only | Never print it, never save it in the project; checked up front so failure is a clear message, not a crash |
| Default model | `nvidia/nemotron-3.5-lightning-30b-a3b` | Nemotron 3.5 Lightning — NVIDIA's 30B MoE model for agentic tasks; free tier available; overridable with `--model` or `/model`. (`nvidia/nemotron-3-super-vl-120b-a12b` was tried first but returned 404 on the integrate endpoint; it may need to be deployed on build.nvidia.com before it can be called.) |
| Display | Chat: user prompts `> `, assistant replies `< `. Headless: raw model output, no prefixes. Tool calls show as `[tool: name]` in both modes. Each model call prints `[context: N tokens]` before sending. | Mirrors Claude Code's `>`/`<` prompt convention so turns are easy to read |
| Modes | Interactive REPL by default; `-p "task"` / `--prompt` for headless | Follows Claude Code conventions |
| Core loop | `CoreLoopService`: non-streaming: call model → append assistant message verbatim → if tool calls, `execute_tool` looks up the service on the Context, runs it, and appends tool results → repeat; stop when the model returns a final text message. Default max 20 tool-calling turns per turn (``TurnLimitReached`` if exceeded). Streaming deferred | Simple, predictable, keeps replies exactly as they came back. Streaming deferred |
| Tool set | `read_file`, `write_file`, `edit_file`, `delete_file`, `list_directory`, `grep_files`, `run_command`, `web_search`, `reload_module`, `code_metrics`, `find_duplicates`, `generate_docs` — each an anima `Service` | `context.py::build_context()` mounts all services on the Context. `service_schema()` derives model-facing tool schemas from each `__call__`. `edit_file`/`reload_module` only work on paths read via `read_file` (per-turn `read_files` set injected by `execute_tool`); `run_command` runs unsandboxed by default (`MAGECODE_SANDBOX=1`/`--sandbox` for Docker); `web_search` uses DuckDuckGo HTML |
| Errors | Missing key → clear message, exit 2. Bad model / API error / network failure → clear message, no traceback (headless exits 1; REPL reports the error and keeps running so the user can `/model` away) | Every failure mode must give a clear message, not a crash |
| Ctrl-C | `KeyboardInterrupt` caught around a turn; prints "Turn interrupted." and returns to the REPL (headless: exits cleanly, code 130) | Stops the current turn, not the program |
| Sandbox | Docker container: `--network none`, `--read-only`, `--user <host UID:GID>`, `--cap-drop ALL`, `no-new-privileges`, CPU/memory/pids limits, `ulimit nofile/fsize`, `--rm`, hard timeout, workdir confined to CWD tree | `run_command` runs unsandboxed by default; sandbox mode is opt-in via `MAGECODE_SANDBOX=1` or `--sandbox`. Fail-closed if Docker CLI/daemon is unavailable in sandbox mode. |
| Testing | Flat unit tests under `tests/unit/` (no `__init__.py`), `AsyncMock` at the OpenAI client seam; `uv run pytest --cov-fail-under=100` | Shared Magitech testing discipline; no real API calls in tests; sandbox tested by mocking the Docker CLI |
| Session instructions | System message written once per session (first message), never rewritten; new info appended at end. Includes rules, system line (OS/folder/date/model), and AGENTS.md if present. `/context` shows context window + token counts. | Keeps the prompt cache valid and the model's reasoning stable across the session |
| Web search | DuckDuckGo HTML + Lite endpoints (both free), `uddg=` URL decoding, multi-signal bot detection. Keyless by design; a self-hosted SearXNG instance (via a future `SEARXNG_URL` option) is the reliable upgrade path. | Research confirmed DDG HTML scraping is fragile (CAPTCHA, 403s, parser drift); live tests from this IP hit bot detection on both endpoints. The tool fails with a clear message rather than silently returning nothing. |

## Tool manuals

Each tool's schema `description` is the manual the model reads before calling it.
Every tool returns text to the model — even failures — and every error says
what to try next.

| Tool | Manual / strict rules |
|---|---|
| `read_file` | Read a file's text. Provide the exact path. Marks the path as readable (required before `edit_file`). On error: fix the path/permissions, retry. |
| `write_file` | Create/overwrite a file. Provide path and full content. Overwrites existing. On error: check path and directory permissions, retry. Marks the path readable. |
| `edit_file` | Replace the first exact `old_string` with `new_string` in a file. **Strict:** the path must have been read via `read_file` first, otherwise refused. `old_string` must match exactly (whitespace/indentation included). If not found: re-read the file to see exact text, retry. |
| `delete_file` | Delete a file. Provide the exact path. Returns confirmation naming the deleted file. On error: check the path, retry. |
| `list_directory` | List directory entries (defaults to `.`). Directories end with `/`. On error: check the path, retry. |
| `grep_files` | Search files for a regex. Provide pattern; optional directory (defaults to `.`). Skips binary/unreadable files. Capped at 50 matches. Returns "No matches." if none. On error: check the directory path, retry. |
| `run_command` | Run a shell command with timeout (default 30s). Runs unsandboxed on the host by default; the user is present and sees every command. Set `MAGECODE_SANDBOX=1` or `--sandbox` for Docker isolation. Returns stdout, stderr, exit code. On timeout/failure: check the command, retry. |
| `web_search` | Search the web via DuckDuckGo (no API key). Provide a query. Tries the HTML endpoint, then the Lite endpoint as a free fallback; decodes DDG's `uddg=` wrappers to real URLs. Returns up to 8 "title: url" results, or a clear bot-detection / no-results / network error. |
| `reload_module` | Hot-reload a Python module from disk. **Strict:** the path must have been read via `read_file` first. Re-executes the module's source file via `importlib`; if reloading `magecode.tools`, updates `_TOOLS` in place so the running harness picks up new tool registrations. On error: check the module name and file path, retry. |
| `code_metrics` | Calculate code quality metrics for Python files in a directory. Provide a directory path (defaults to `.`). Returns lines of code, blank/comment lines, function/class counts, estimated cyclomatic complexity. On error: check the directory path, retry. |
| `find_duplicates` | Find duplicate code blocks across Python files. Provide a directory path (defaults to `.`) and optional `min_lines` (defaults to 3). Returns matching blocks with file paths and line numbers. On error: check the directory path, retry. |
| `generate_docs` | Generate markdown documentation from Python docstrings and comments. Provide a directory path (defaults to `.`). Lists classes and public functions with their docstrings. On error: check the directory path, retry. |

## Tools as anima components

Each tool is an anima `Service` in its own file under `src/magecode/tools/`,
with the filename matching the tool name (e.g. `read_file.py` defines
`ReadFileService`). A tool registers itself by name in `__init__`:

```python
from anima import Context, Service


class MyToolService(Service):
    """Do something useful.

    Args:
        argument: What the argument is for.
    """

    def __init__(self, ctx: Context):
        super().__init__(ctx, "my_tool")

    def __call__(self, *, argument: str) -> str:
        return f"Did something with {argument}"
```

`service_schema()` builds the model-facing JSON schema from the class:

* Tool name from the explicit name passed to `super().__init__` (via
  `build_context`, which passes `impl.name` to `service_schema`)
* Tool description from the class docstring summary (first paragraph)
* Parameter descriptions from the docstring `Args:` section
* Parameter types and requiredness from the `__call__` signature annotations
* `self` / `cls` / `read_files` are excluded (`read_files` is injected at call
  time by `execute_tool`)

Wiring a new tool requires: define the Service class, re-export it in
`tools/__init__.py`, and add it to `TOOL_SERVICES` in `context.py`. No separate
registry edits — schema and execution both come from the Service.

## Read-before-edit rule

The turn loop tracks a `read_files` set per turn, which `execute_tool` injects
into any tool whose `__call__` accepts it. `edit_file` and `reload_module` are
refused for any path not in that set. The model must call `read_file` on a path
before it can `edit_file` that path or `reload_module` a module at that path.
`write_file` also marks a path readable (the model authored the content).

## Error contract

Every tool call gets an answer. Failures return text starting with "Error:" or
"Refused:" plus a "what to try next" instruction. The turn never crashes on a
tool error; the result is fed back to the model as a `tool` message and the
loop continues.

## Session instructions

The model sees a system message (`messages[0]`) on every call. It is written
once per session and never rewritten; new information is appended at the end so
the prompt cache stays valid and the model's reasoning remains stable.

The system message contains:

1. **Rules** — short behavioral rules for the coding agent.
2. **System line** — OS, working folder, date, and model ID.
3. **AGENTS.md** — if the project has an `AGENTS.md`, its full content is
   appended after a separator.

### `/context` command

In interactive chat, `/context` prints the full context window: every message
with its role, a content preview, and any tool calls, plus the total token
count (cl100k_base encoding) before each model call.

## File layout

- `pyproject.toml` — metadata, dependencies (`anima`, `openai`), entry point `magecode`
- `src/magecode/__init__.py`
- `src/magecode/context.py` — builds the anima Context; mounts all services (`TOOL_SERVICES`)
- `src/magecode/client.py` — NVIDIA/OpenAI-compatible client, key validation
- `src/magecode/instructions.py` — system message builder, token counting
- `src/magecode/core_loop.py` — `CoreLoopService`: core model ↔ tool loop
- `src/magecode/tools/` — anima Service components, one file per tool
  - `__init__.py` — re-exports tool Service classes
  - `registry.py` — `service_schema()` inference from Service `__call__`
  - `executor.py` — `execute_tool()` (looks up services on the Context)
  - `read_file.py`, `write_file.py`, `edit_file.py`, `delete_file.py`,
    `list_directory.py`, `grep_files.py`, `run_command.py`,
    `web_search.py`, `code_metrics.py`, `find_duplicates.py`,
    `generate_docs.py`, `reload_module.py` — one `Service` per tool
- `src/magecode/repl.py` — interactive chat + `/model` + `/context`
- `src/magecode/cli.py` — argparse: `-p`, `--model`, `--sandbox`
- `DESIGN.md` — this file
- `tests/unit/*.py` — unit tests; `tests/integration/` — live Docker tests
