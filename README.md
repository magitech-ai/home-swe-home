# magecode

A small coding agent in Python: a mini Claude Code. Core loop — send the task
to the model, run the tools the model asks for, send the results back, repeat
until the model stops asking. Model replies are printed exactly as they came
back.

## Setup

```sh
uv sync                      # install dependencies and this package
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

In chat, `/model <id>` switches models; Ctrl-C aborts the current turn only;
Ctrl-D exits.

## Design

See `DESIGN.md` for how to run, setup, and every decision.
