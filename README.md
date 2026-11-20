# home-swe-home

**New here? Read [START_HERE](https://github.com/magitech-ai/agents-home/blob/main/START_HERE.md).**
It explains where the factory, decision log, evidence and audit records live.

A small coding agent built on the [anima](https://github.com/magitech-ai/anima)
micro-kernel. Everything is a
component: the core loop and all 15 tools are anima Services mounted on a
Context. Core loop — send the task to the model, run the tools the model asks
for, send the results back, repeat until the model stops asking. Model replies
are printed exactly as they came back.

## Setup

```sh
uv sync                      # installs anima + dependencies and this package
export GEMINI_API_KEY=...        # default provider is Gemini; or export NVIDIA_API_KEY and set HOME_SWE_HOME_PROVIDER=nvidia
```

Set `HOME_SWE_HOME_PROVIDER=gemini` and export `GEMINI_API_KEY` (or
`GOOGLE_API_KEY`) to use Gemini's OpenAI-compatible endpoint; choose the model
with `--model` or `HOME_SWE_HOME_MODEL`.

## Run

`hsh` is a short alias for `home-swe-home`; both run the same CLI.

```sh
# Headless: one task and exit
uv run home-swe-home -p "say hi in three words"

# Interactive chat (default)
uv run home-swe-home

# Pick a model
uv run home-swe-home --model gemini-4-hydrogen --effort medium -p "..."
```

Gemini has two API modes under `HOME_SWE_HOME_PROVIDER=gemini`: native
Interactions (default, `HOME_SWE_HOME_GEMINI_API=interactions`) and the
OpenAI-compatible endpoint (`HOME_SWE_HOME_GEMINI_API=openai`). Native mode supports
readable thought summaries; show them with `--show-reasoning` or
`HOME_SWE_HOME_SHOW_REASONING=1` (display only — never stored in context). All native
events are translated and unknown ones are printed as `UNKNOWN:` so new upstream
events are visible.

Replies stream token-by-token by default; pass `--no-stream` to wait for the full reply. Known provider events are quiet by default; `--show-events` (or `HOME_SWE_HOME_SHOW_EVENTS=1`) prints them, while unknown event types are always printed as `UNKNOWN:`.

In chat, `/model <id>` switches models, `/skill <name>` loads a skill's full
instructions, and `/context` shows the context window. Ctrl-C aborts the
current turn only; Ctrl-D exits.

Shell commands run unsandboxed on the host by default. Pass `--sandbox` or set
`HOME_SWE_HOME_SANDBOX=1` to run them inside an isolated Docker container.

The base prompt and per-tool guidance are editable data files under
`src/home_swe_home/harness/`. To try a modified copy without editing the installed
package, set `HOME_SWE_HOME_HARNESS_DIR` to a directory containing `systemprompt.md`
and `tool_guidance.md`.

`HOME_SWE_HOME_CONFIG_PATH` isolates config for testing; `--dry-run` with `--init-home` scaffolds and records config without GitHub writes. `--plan` prints (optionally as `--json`) exactly what would happen without writing anything; `--yes` confirms non-interactively for agents/scripts; `--force` is required if a home checkout already exists, so onboarding never silently replaces the real home.

First-time setup (no home checkout yet):

```sh
uv run home-swe-home --init-home --home-repo <owner>/agents-home
```

This scaffolds a home checkout (offering `~/.agents/agents-home` as the
default path), provisions the private GitHub repo via `gh`, and records the
path in `~/.agents/home-swe-home/config.toml`. Every remote step is confirmed.

## Design

See `DESIGN.md` for how to run, setup, and every decision.
