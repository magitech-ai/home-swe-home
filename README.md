# magecode

A small coding agent built on the [anima](https://github.com/magitech-ai/anima)
micro-kernel. Everything is a
component: the core loop and all 15 tools are anima Services mounted on a
Context. Core loop — send the task to the model, run the tools the model asks
for, send the results back, repeat until the model stops asking. Model replies
are printed exactly as they came back.

## Setup

```sh
uv sync                      # installs anima + dependencies and this package
export GEMINI_API_KEY=...        # default provider is Gemini; or export NVIDIA_API_KEY and set MAGECODE_PROVIDER=nvidia
```

Set `MAGECODE_PROVIDER=gemini` and export `GEMINI_API_KEY` (or
`GOOGLE_API_KEY`) to use Gemini's OpenAI-compatible endpoint; choose the model
with `--model` or `MAGECODE_MODEL`.

## Run

```sh
# Headless: one task and exit
uv run magecode -p "say hi in three words"

# Interactive chat (default)
uv run magecode

# Pick a model
uv run magecode --model gemini-4-hydrogen --effort medium -p "..."
```

Gemini has two API modes under `MAGECODE_PROVIDER=gemini`: native
Interactions (default, `MAGECODE_GEMINI_API=interactions`) and the
OpenAI-compatible endpoint (`MAGECODE_GEMINI_API=openai`). Native mode supports
readable thought summaries; show them with `--show-reasoning` or
`MAGECODE_SHOW_REASONING=1` (display only — never stored in context). All native
events are translated and unknown ones are printed as `UNKNOWN:` so new upstream
events are visible.

Replies stream token-by-token by default; pass `--no-stream` to wait for the full reply. Known provider events are quiet by default; `--show-events` (or `MAGECODE_SHOW_EVENTS=1`) prints them, while unknown event types are always printed as `UNKNOWN:`.

In chat, `/model <id>` switches models, `/skill <name>` loads a skill's full
instructions, and `/context` shows the context window. Ctrl-C aborts the
current turn only; Ctrl-D exits.

Shell commands run unsandboxed on the host by default. Pass `--sandbox` or set
`MAGECODE_SANDBOX=1` to run them inside an isolated Docker container.

The base prompt and per-tool guidance are editable data files under
`src/magecode/harness/`. To try a modified copy without editing the installed
package, set `MAGECODE_HARNESS_DIR` to a directory containing `systemprompt.md`
and `tool_guidance.md`.

`MAGECODE_CONFIG_PATH` isolates config for testing; `--dry-run` with `--init-home` scaffolds and records config without GitHub writes. `--plan` prints (optionally as `--json`) exactly what would happen without writing anything; `--yes` confirms non-interactively for agents/scripts; `--force` is required if a home checkout already exists, so onboarding never silently replaces the real home.

First-time setup (no home checkout yet):

```sh
uv run magecode --init-home --home-repo <owner>/agents-home
```

This scaffolds a home checkout (offering `~/.agents/agents-home` as the
default path), provisions the private GitHub repo via `gh`, and records the
path in `~/.agents/magecode/config.toml`. Every remote step is confirmed.

## Design

See `DESIGN.md` for how to run, setup, and every decision.
