# home-swe-home

**New here? Read [START_HERE](https://github.com/magitech-ai/agents-home/blob/main/START_HERE.md).**
It explains where the factory, decision log, evidence and audit records live.

A small coding agent built on the [anima](https://github.com/magitech-ai/anima)
micro-kernel and [magitech-harness](https://github.com/magitech-ai/magitech-harness),
the composable agent runtime. Everything is a component: the turn engine, session
log, tool registry and LLM seam come from mth, and all 15 tools are mth
`ToolDefinition`s mounted on a Context. Core loop — send the task to the model,
run the tools the model asks for, send the results back, repeat until the model
stops asking.

## Setup

```sh
uv sync                      # installs anima + dependencies and this package
export GEMINI_API_KEY=...        # default provider is Gemini
```

Set `HOME_SWE_HOME_PROVIDER=gemini` and export `GEMINI_API_KEY` (or
`GOOGLE_API_KEY`) to use Gemini's OpenAI-compatible endpoint; choose the model
with `--model` or `HOME_SWE_HOME_MODEL`.

For a tool-capable provider, set `HOME_SWE_HOME_PROVIDER=openrouter` and export
`OPENROUTER_API_KEY`. The OpenRouter adapter is bound to `tencent/hy4-flash`
with `reasoning.effort = "high"`; this is the only route that adapter serves.
Select it explicitly with:

```sh
HOME_SWE_HOME_PROVIDER=openrouter uv run home-swe-home -p "..."
```

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

## Improve the harness

`hsh-improve` runs one measured Propose–Probe–Compose cycle: a model proposes a
rewrite of the editable harness, the candidate and base arms are run on the
fixed task suite, and the candidate is adopted only on a strict pass-rate win.

```sh
export HOME_SWE_HOME_PROPOSER_MODEL=nvidia/nemotron-3.5-super-vl:free
uv run hsh-improve "make skill loading more reliable" --domain coding --trials 1
```

It writes a JSON report to stdout (or `--out FILE`), and on a win writes the
adopted tree to `<work-dir>/adopted` plus a lesson in the domain library.
Nothing is promoted into the installed package automatically. Each candidate
costs two CLI rollouts per task per trial, so start with `--trials 1`.

The agent uses Gemini's native Interactions API. Its readable thought summaries
can be displayed with `--show-reasoning` or `HOME_SWE_HOME_SHOW_REASONING=1`
(display only — never stored in context). All native
events are translated and unknown ones are printed as `UNKNOWN:` so new upstream
events are visible.

Replies stream token-by-token. Pass `--show-reasoning` (or
`HOME_SWE_HOME_SHOW_REASONING=1`) to also print provider thought summaries;
reasoning is displayed only and never stored in context.

In chat, `/model <id>` switches models, `/skill <name>` loads a skill's full
instructions, and `/context` shows the context window with a per-message preview and token estimate. Ctrl-C aborts the
current turn only; Ctrl-D exits.

Shell commands run inside an isolated Docker container by default (`--network
none`, read-only root, dropped capabilities, resource limits). Pass
`--no-sandbox` or set `HOME_SWE_HOME_SANDBOX=0` to run them on the host instead —
host mode has your full privileges, including environment variables.

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
