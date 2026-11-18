# magecode

A small coding agent built on the [anima](https://github.com/magitech-ai/anima)
micro-kernel (Magitech's Python implementation of Cordis). Everything is a
component: the core loop and all 14 tools are anima Services mounted on a
Context. Core loop — send the task to the model, run the tools the model asks
for, send the results back, repeat until the model stops asking. Model replies
are printed exactly as they came back.

## Setup

```sh
uv sync                      # installs anima + dependencies and this package
export NVIDIA_API_KEY=nvapi-...   # https://build.nvidia.com; never echo it
```

## Run

```sh
# Headless: one task and exit
uv run magecode -p "say hi in three words"

# Interactive chat (default)
uv run magecode

# Pick a model
uv run magecode --model nvidia/nemotron-3.5-lightning-30b-a3b -p "..."
```

In chat, `/model <id>` switches models, `/skill <name>` loads a skill's full
instructions, and `/context` shows the context window. Ctrl-C aborts the
current turn only; Ctrl-D exits.

Shell commands run unsandboxed on the host by default. Pass `--sandbox` or set
`MAGECODE_SANDBOX=1` to run them inside an isolated Docker container.

The base prompt and per-tool guidance are editable data files under
`src/magecode/harness/`. To try a modified copy without editing the installed
package, set `MAGECODE_HARNESS_DIR` to a directory containing `systemprompt.md`
and `tool_guidance.md`.

First-time setup (no home checkout yet):

```sh
uv run magecode --init-home --home-repo <owner>/agents-home
```

This scaffolds a home checkout (offering `~/.agents/agents-home` as the
default path), provisions the private GitHub repo via `gh`, and records the
path in `~/.agents/magecode/config.toml`. Every remote step is confirmed.

## Design

See `DESIGN.md` for how to run, setup, and every decision.
