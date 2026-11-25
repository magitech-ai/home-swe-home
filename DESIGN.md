# Design doc — home-swe-home

A small coding agent in Python. Core loop — send the task to the model, run the
tools the model asks for, send the results back, and repeat until the model
stops asking. Model replies are printed exactly as they came back.

## How to run

```sh
# From this repo root
uv sync                      # install deps + this package
export NVIDIA_API_KEY=nvapi-...   # see "API key setup" below; never echo this

# Headless: one task, nobody watching (requires your key)
uv run home-swe-home -p "say hi in three words"

# Interactive chat (default)
uv run home-swe-home

# Pick a model
uv run home-swe-home --model nvidia/nemotron-3.5-lightning-30b-a3b -p "..."
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
| Foundation | **animas** micro-kernel | "Everything is a component": every capability is an animas Service on a Context. Matches the ecosystem (magitech-harness, mth-components) and the component pattern's proven scale. You control animas, so API changes are coordinateable. |
| Language / runtime | Python 3.12+, `uv`-managed | animas requires 3.12+. Shared Magitech standards; strict mypy, ruff (line length 88), pytest |
| API | Gemini Interactions API (native, via `google-genai`) | The agent loop reaches the model through mth's `ctx.llm`; `GeminiAdapter` translates Interactions stream events into mth `StreamChunk`s |
| Auth | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | Never printed or persisted; checked up front so failure is a clear message, not a crash |
| Default model | `gemini-4-hydrogen` | Overridable with `--model` or `/model` |
| Display | Chat: user prompts `> `, assistant replies `< `. Headless: raw model output, no prefixes. Tool calls show as `[tool: name]` in both modes. Each model call prints `[context: N tokens]` before sending. | Mirrors Claude Code's `>`/`<` prompt convention so turns are easy to read |
| Modes | Interactive REPL by default; `-p "task"` / `--prompt` for headless | Follows Claude Code conventions |
| Core loop | mth's `ReactLoopAgent` via `ctx.agents.create` → `agent.followup` → `agent.when_idle`. Send the task, run the requested tools, feed results back, repeat until the model stops asking. Turn/step boundaries, cancellation and tool-pairing integrity come from mth | The turn engine is the hardened substrate, not a parallel implementation |
| Tool set | `read_file`, `write_file`, `edit_file`, `delete_file`, `list_directory`, `grep_files`, `run_command`, `web_search`, `reload_module`, `code_metrics`, `find_duplicates`, `generate_docs`, `add_repo`, `verify_repo` — each an mth `ToolDefinition` registered via `ctx.tools.register(define_tool({...}))` in `tools/definitions.py`. Skill loading moved to the mth-components `skill({name})` tool; OKF bundles load via `okf_bundle({name})`. | Every capability is still a component, but the component is now an mth tool definition rather than an animas Service. `edit_file`/`reload_module` only work on paths read via `read_file` during the *current turn* (reconstructed from the session log by `_current_turn_read_paths`); `run_command` runs **sandboxed by default** (`--no-sandbox`/`HOME_SWE_HOME_SANDBOX=0` for host execution); `web_search` uses SearXNG then DuckDuckGo. Every tool's text result is redacted at the `output.render` boundary so no tool can leak a secret |
| Errors | Missing key → clear message, exit 2. Bad model / API error / network failure → clear message, no traceback (headless exits 1; REPL reports the error and keeps running so the user can `/model` away) | Every failure mode must give a clear message, not a crash |
| Ctrl-C | `KeyboardInterrupt` caught around a turn; prints "Turn interrupted." and returns to the REPL (headless: exits cleanly, code 130) | Stops the current turn, not the program |
| Sandbox | Docker container: `--network none`, `--read-only`, `--user <host UID:GID>`, `--cap-drop ALL`, `no-new-privileges`, CPU/memory/pids limits, `ulimit nofile/fsize`, `--rm`, hard timeout, workdir confined to CWD tree | `run_command` runs **sandboxed by default**; host execution is opt-in via `HOME_SWE_HOME_SANDBOX=0` or `--no-sandbox`. Fail-closed if the Docker CLI/daemon is unavailable in sandbox mode. |
| Testing | Flat unit tests under `tests/unit/` (no `__init__.py`), `AsyncMock` at the OpenAI client seam; `uv run pytest --cov-fail-under=100` | Shared Magitech testing discipline; no real API calls in tests; sandbox tested by mocking the Docker CLI |
| Session instructions | System message written once per session (first message), never rewritten; new info appended at end. Includes rules, system line (OS/folder/date/model), and AGENTS.md if present. `/context` shows context window + token counts. | Keeps the prompt cache valid and the model's reasoning stable across the session |
| Web search | If `SEARXNG_URL` is set, query that self-hosted instance's JSON API first (must have `search.formats: [json]` enabled); a 403/network error/malformed JSON falls back to DuckDuckGo. Otherwise DuckDuckGo HTML + Lite endpoints, `uddg=` URL decoding, multi-signal bot detection. Keyless by design. | Research confirmed DDG HTML scraping is fragile (CAPTCHA, 403s, parser drift); live tests from this IP hit bot detection on both endpoints. SearXNG is the reliable keyless upgrade, optional so the default stays zero-config. |

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
| `run_command` | Run a shell command with timeout (default 30s). Runs inside a Docker sandbox by default; pass `HOME_SWE_HOME_SANDBOX=0` or `--no-sandbox` to run on the host (full user privileges). Returns stdout, stderr, exit code. On timeout/failure: check the command, retry. |
| `web_search` | Search the web with no API key. If `SEARXNG_URL` is set, uses that instance's JSON API first (403/error falls back). Otherwise tries DuckDuckGo HTML, then Lite; decodes `uddg=` wrappers to real URLs. Returns up to 8 "title: url" results, or a clear bot-detection / no-results / network error. |
| `reload_module` | Hot-reload a Python module from disk. **Strict:** the path must have been read via `read_file` first. Re-executes the module's source file via `importlib`; if reloading `home-swe-home.tools`, updates `_TOOLS` in place so the running harness picks up new tool registrations. On error: check the module name and file path, retry. |
| `code_metrics` | Calculate code quality metrics for Python files in a directory. Provide a directory path (defaults to `.`). Returns lines of code, blank/comment lines, function/class counts, estimated cyclomatic complexity. On error: check the directory path, retry. |
| `find_duplicates` | Find duplicate code blocks across Python files. Provide a directory path (defaults to `.`) and optional `min_lines` (defaults to 3). Returns matching blocks with file paths and line numbers. On error: check the directory path, retry. |
| `generate_docs` | Generate markdown documentation from Python docstrings and comments. Provide a directory path (defaults to `.`). Lists classes and public functions with their docstrings. On error: check the directory path, retry. |

## Tools as mth components

Each tool is an mth `ToolDefinition` built with `define_tool({...})` and
registered on `ctx.tools`. All 15 live in `tools/definitions.py`; each declares
its name, description, parameter schema, output schema and renderer, and an
`execute(args, run_ctx)` handler:

```python
from magitech_harness.tools import define_tool

READ_FILE = define_tool(
    {
        "name": "read_file",
        "description": "Read a file and return its text contents.",
        "parameters": {"path": {"type": "string", "required": True}},
        "isConcurrencySafe": lambda _args: True,
        "output": {
            "schema": {"type": "string"},
            "render": lambda _args, val: [{"type": "text", "text": val}],
        },
        "execute": _read_file_execute,
    }
)
```

The `execute` handler receives `(args, run_ctx)` where `run_ctx` carries
`signal`, `callId`, `agent`, `deferContext`, and `concludeTurn` from mth's tool
pipeline. mth validates arguments against the declared schema, routes the call
through the `tools/pre-execute` → execute → `tools/post-execute` waterfall, and
projects the result into model-visible content.

Wiring a new tool requires: build the `ToolDefinition`, add it to `ALL_TOOLS` in
`tools/definitions.py`, and it is registered on the context by `register_tools()`.
mth derives the model-facing schema from the definition — there is no separate
schema registry.

The `read_files` tracker from the original animas-based tools is gone: tools that
need to know whether a path was read reconstruct it from the session event log
via `_current_turn_read_paths`, scoped to the current turn.

## Measuring improvement

Harness candidates are adopted only when an A/B evaluation shows a pass-rate
gain on a fixed task suite. `eval.py` runs each task against a base or candidate
harness via `HOME_SWE_HOME_HARNESS_DIR` and records per-task outcomes; `improve.py`
supplies the candidate. Source-code self-improvement is not attempted until a
harness change is measured to help.

Tool results are redacted at the `output.render` boundary so a model cannot
extract API keys by asking a tool to read `.env`, print the environment, or
grep for a token prefix.

`BUILTIN_TASKS` is too easy — tool-prescribing prompts score at ceiling and
cannot discriminate. `HARD_TASKS` uses outcome checkers instead (including
`contains_all` and `count_at_least`) and is the suite used for adoption
decisions. A single hung rollout is recorded as a failure by `cli_runner`
rather than aborting the run. `evaluate` separates infrastructure errors
(`NVIDIA API error`, `[timed out]`) from task failures and excludes them from
the pass-rate denominator; `compare_arms` interleaves the two arms so time
drift and provider rate limits affect both equally.

An interleaved 3-trial run on 2026-11-18 was inconclusive: 34/36 trials were
NVIDIA 429 responses, leaving one valid trial per arm. No adoption decision was
made from it.

Gemini is available as a second provider (`HOME_SWE_HOME_PROVIDER=gemini`, key in
`GEMINI_API_KEY`, model via `HOME_SWE_HOME_MODEL`). Gemini thinking models return an
encrypted `extra_content.google.thought_signature` on tool calls; the assistant
message converter preserves it verbatim or the next turn fails with HTTP 400.

On `gemini-4-neon`, an interleaved 3-trial A/B of the isolated `## load_skill`
guidance measured base 11/13 (0.846) vs candidate 9/11 (0.818), delta -0.028.
The candidate was **not adopted**. No harness change tested so far has produced
a reproducible general-capability gain; the only positive result was a synthetic
canary that encoded its own answer in the candidate prompt.

Measured 2026-11-18, four trials per arm: base 20/24 (0.833), a prompt targeted
at the observed failures 22/24 (0.917), delta +0.083. The gain came entirely
from `skill-router` (1/4 → 4/4); the targeted arm lost two `repo-count` trials
that base passed, so the sample is small and the change was not auto-adopted.
Earlier "call tools verbatim", "never call tools" and canary-only arms produced
no defensible general-capability gain and were not adopted.

`improve.run_cycle()` probes every candidate with the evaluator, selects a
strict winner (`utils/selection.py`), composes per-file from the best candidate
that changed each file, and persists the adopted tree plus a `cue`/`lesson`/
`evidence` entry in a per-domain `library.Library`. Ties and regressions keep
the base harness; invalid candidates never reach composition.

`orchestrate.run_cycle()` drives that step end to end as the external
Propose–Probe–Compose loop: it asks an injected proposer for a candidate tree
(shaped by the current harness and the domain library index), validates it
before any inference is spent, probes candidate against base with an
interleaved evaluator, and on a strict pass-rate win composes, persists, and
records the lesson. `orchestrate.build_proposer()` adapts a single-shot
`ask(prompt) -> text` callable into a proposer, and `orchestrate.default_ask()`
implements it against the configured provider, so the loop needs no separate
credentials. A cycle returns a `CycleReport` carrying the scores, the
selection reason, and whether anything was adopted — a rejection is reported,
never silently dropped.

## Streaming

`GeminiAdapter` opens the native Interactions stream and translates events into
mth `StreamChunk`s (`block-start`, `text-delta`, `reasoning-delta`,
`tool-call-delta`, `usage`, `finish`); mth's `AssistantStreamAttempt`
accumulates them into a durable assistant message. Reasoning deltas are
displayed but never written to the session log, so `--show-reasoning` is
presentation only. The REPL renders streaming from `agent/assistant-stream`
events.

## Defaults

The default provider is Gemini, model `gemini-4-hydrogen`, effort `medium`.
`HOME_SWE_HOME_MODEL`, `--model`, `HOME_SWE_HOME_EFFORT` and `--effort` override them.
OpenAI-compatible Gemini calls send `reasoning_effort`; native Interactions
calls send `generation_config.thinking_level`. Set
`HOME_SWE_HOME_PROVIDER=nvidia` to use the NVIDIA endpoint.

## Gemini API modes

`HOME_SWE_HOME_PROVIDER=gemini` defaults to the native Interactions API
(`HOME_SWE_HOME_GEMINI_API=interactions`) using the official `google-genai` SDK.
`HOME_SWE_HOME_GEMINI_API=openai` keeps the OpenAI-compatible endpoint as a fallback.
Native stateful calls carry `previous_interaction_id` and `store=True`, so
thought signatures are managed server-side; function results are sent as
`function_result` blocks. `utils/native_events.py` translates **every** event
and delta type in the v1beta reference (8 event types, 24 delta types): text,
reasoning and tool calls map to home-swe-home's message shape; other events are
recorded and printed as `[event: ...]`, and unrecognised ones are labelled
`UNKNOWN:` instead of being silently dropped.

`--show-reasoning` / `HOME_SWE_HOME_SHOW_REASONING=1` prints `thought_summary` deltas
between `[reasoning]` markers. Reasoning is display-only and never added to
message history.

## Editable harness

The system prompt and per-tool guidance are data files under
`src/home_swe_home/harness/`, not Python constants. `instructions.base_instructions()`
reads `systemprompt.md` and registers it as the `hsh:identity` system-prompt
section; `utils/harness.tool_guidance(name)` is available for per-tool guidance.

An outer improvement loop can roll out a candidate harness without editing the
installed package by setting `HOME_SWE_HOME_HARNESS_DIR` to a copy of the tree.
The loader (`utils/harness.py`) allowlists the two filenames, so a candidate
cannot redirect reads elsewhere. `orchestrate.run_cycle()` implements the
Propose–Probe–Compose step: it reads a base tree, applies an injected proposer,
validates against the editable surface *before spending any inference*,
materialises the candidate, probes candidate against base with an interleaved
evaluator, and on a strict pass-rate win composes, persists, and records the
lesson in the domain `Library`. The loop is a library for an external
orchestrator, not an animas Service.

In home-first mode the **home repo's** `harness/` tree is authoritative; the
packaged copy is only a template for `--init-home` scaffolding. See ADR 0004.

## Home-first agent architecture

home-swe-home is the agent run *from* `agents-home`, taking over the role that
`agents-home/README.md` currently describes as a convention ("Start agent
sessions here when a task may span multiple repositories"). It is not a
standalone any-cwd agent: the home repo is always its starting point.

**Home resolution, in order:**

1. `~/.agents/home-swe-home/config.toml` — absolute `home_path` plus repo identity. Authoritative; this is what makes "config on `/home`, checkout on a different SSD" work.
2. `AGENTS_HOME_PATH` environment override.
3. Name-based walk-up from cwd looking for a directory named `agents-home` with `AGENTS.md`, `skills/` and the `## Other Repos` map.

`HOME_SWE_HOME_HARNESS_DIR` is unrelated: it swaps a candidate harness tree for a
rollout, not the home location.

**Onboarding.** If no home is found, a wizard (human-only steps) runs: `gh auth
login` if needed, choose a local path (offered default `~/.agents/agents-home`,
always confirmed), scaffold from packaged templates, offer `gh repo create
--private` plus initial push with explicit consent, then write the config. An
existing checkout skips all of this — it is treated as if onboarding had
already recorded it. Tokens stay in the `gh` credential store, never in config.

**What the home repo provides:** the authoritative harness tree, the canonical
skills collection, the curated `## Other Repos` map (sibling paths + clone
URLs), shared `AGENTS.md`, and the org's GitHub workflow conventions.

**Multi-repo work** is map-driven: a GitHub link or local directory resolves
through the map; missing repos are cloned as siblings only after confirmation;
map edits go through a PR; each target repo's `AGENTS.md` is layered into the
session; each affected repo's own checks must pass before the task is done.
Execution uses one context initially — no sub-agents until evidence demands
isolation.

**Skills** follow agentskills.io (ADR 0005). Discovery roots: `agents-home/skills/`
(native/client scope, authoritative), `~/.agents/skills/` (cross-client user
scope), `<project>/.agents/skills/` (project-local, default-deny until trusted).
No `~/.home-swe-home/skills`. The catalog is `name` + `description` only, with no
cap and no truncation; the planned seeker-rune component will address catalog
budget later.

**Phases:** (1) home-mode foundation — config/discovery, onboarding wizard,
layered instructions, repo map, `gh` workflow, per-repo verification; (2)
conformant skill integration; (3) the external Propose–Probe–Compose loop.

## Read-before-edit rule

`edit_file` and `reload_module` are refused for any path not read or written
*during the current turn*. The set is reconstructed from the session event log by
`_current_turn_read_paths` (scoped by the last `turn/start`), so a file read in
turn 1 does not authorize an edit in turn 50. The model must call `read_file` on
a path before it can `edit_file` that path or `reload_module` a module at that
path. `write_file` also marks a path readable (the model authored the content).

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
4. **Skills & Reminders (tail)** — the mth-components `skills-loader` injects
   the model-facing Agent Skills catalog (from `skills_registry`) and
   `okf-loader` injects the OKF knowledge-bundle catalog, both as
   `<system-reminder>` sections; in interactive REPL mode only,
   `RemindersService.due_block()` is appended last to preserve the prompt cache
   prefix. Headless `-p` mode omits reminders by default so one-off and
   automated tasks stay deterministic.

### `/context` and `/reminders` commands

In interactive chat, `/context` prints the full context window: every message
with its role, a content preview, and any tool calls, plus the total token
count (cl100k_base encoding) before each model call. `/reminders` prints a
read-only summary of due, upcoming, and auto-resolved passive reminders from
`<agents-home>/reminders.local.toml` and `<agents-home>/reminders.toml`.

## File layout

- `pyproject.toml` — metadata, dependencies (`animas`, `openai`), entry point `home-swe-home`
- `src/home_swe_home/__init__.py`
- `src/home_swe_home/context.py` — calls `create_harness()`, mounts app services, registers the Gemini adapter, the 15 tools, and prompt sections
- `src/home_swe_home/llm/gemini_adapter.py` — `GeminiAdapter` (Interactions API → mth `StreamChunk`)
- `src/home_swe_home/providers.py` — provider config for the standalone review/audit tools
- `src/home_swe_home/instructions.py` — pure system-prompt helpers (base prompt, system line, AGENTS.md)
- `src/home_swe_home/reminders.py` — `RemindersService` (read-only passive reminder discovery)
- `src/home_swe_home/harness/` — editable harness data (not code): `systemprompt.md`
  (base prompt), `tool_guidance.md` (`## <tool_name>` sections appended to tool
  descriptions). `HOME_SWE_HOME_HARNESS_DIR` swaps in a candidate tree for rollouts.
- `src/home_swe_home/sandbox.py` — `SandboxService` (process confinement)
- `src/home_swe_home/orchestrate.py` — the external Propose–Probe–Compose improvement loop
- `src/home_swe_home/improve_cli.py` — `hsh-improve`, the CLI that drives one cycle
- `src/home_swe_home/tools/definitions.py` — all 14 tools as mth `ToolDefinition`s
  - `__init__.py` — re-exports `ALL_TOOLS` and `register_tools`
  - `executor.py` — `ToolService` mounted as `ctx.tools`
  - Skill loading is not a home-swe-home tool: it is the mth-components
    `skills-loader` service (`skill({name})`), and Agent Skills + OKF bundles
    are handled entirely by the six mth-components bridges in `mth-components`.
- `src/home_swe_home/utils/` — pure helpers (the documented exception to "everything
  is a component"): `schema.py` (JSON-schema inference), `text.py` (shared
  decoder), `harness.py` (readers for the editable harness tree). Stateless,
  no lifecycle.
- `src/home_swe_home/repl.py` — interactive chat + `/model` + `/context`
- `src/home_swe_home/cli.py` — argparse: `-p`, `--model`, `--no-sandbox`, `--show-reasoning`
- `DESIGN.md` — this file
- `tests/unit/*.py` — unit tests; `tests/integration/` — live Docker tests
