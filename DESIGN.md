# Design doc — mini-claude

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
uv run mini-claude -p "say hi in three words"

# Interactive chat (default)
uv run mini-claude

# Pick a model
uv run mini-claude --model meta/llama-3.1-8b-instruct -p "..."
```

Inside chat, `/model meta/llama-3.1-8b-instruct` switches models for the rest of
the session. Ctrl-C aborts the current turn only.

## API key setup

1. Sign in at https://build.nvidia.com and create an API key (starts with
   `nvapi-`).
2. Export it in your shell, for this session only:

   ```sh
   export NVIDIA_API_KEY=nvapi-...
   ```

   Do not echo it, do not write it into this project, and do not commit it.
   This project reads `NVIDIA_API_KEY` from the environment and never touches
   `.env` files.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / runtime | Python 3.14+, `uv`-managed | Shared Magitech standards; strict mypy, ruff (line length 88), pytest |
| API | NVIDIA build.nvidia.com, OpenAI-compatible, `https://integrate.api.nvidia.com/v1` | User's Nvidia API key; the `openai` Python client speaks this protocol natively |
| Auth | `NVIDIA_API_KEY` environment variable only | Never print it, never save it in the project; checked up front so failure is a clear message, not a crash |
| Default model | `nvidia/nemotron-3.5-lightning-30b-a3b` | Nemotron 3.5 Lightning — NVIDIA's 30B MoE model for agentic tasks; free tier available; overridable with `--model` or `/model`. (`nvidia/nemotron-3-super-vl-120b-a12b` was tried first but returned 404 on the integrate endpoint; it may need to be deployed on build.nvidia.com before it can be called.) |
| Modes | Interactive REPL by default; `-p "task"` / `--prompt` for headless | Follows Claude Code conventions |
| Core loop | Non-streaming: call model → append assistant message verbatim → if tool calls, execute each and append tool results → repeat; stop when the model returns a final text message | Simple, predictable, keeps replies exactly as they came back. Streaming deferred |
| Tool set | `read_file`, `write_file`, `list_directory`, `grep_files`, `run_command` | Minimal useful coding-agent tools; `run_command` runs with a timeout in the current working directory (not sandboxed — local personal agent, use with care) |
| Errors | Missing key → clear message, exit 2. Bad model / API error / network failure → clear message, no traceback (headless exits 1; REPL reports the error and keeps running so the user can `/model` away) | Every failure mode must give a clear message, not a crash |
| Ctrl-C | `KeyboardInterrupt` caught around a turn; prints "Turn interrupted." and returns to the REPL (headless: exits cleanly, code 130) | Stops the current turn, not the program |
| Testing | Flat unit tests under `tests/unit/` (no `__init__.py`), `AsyncMock` at the OpenAI client seam; `uv run pytest --cov-fail-under=100` | Shared Magitech testing discipline; no real API calls in tests |

## File layout

- `pyproject.toml` — metadata, dependencies (`openai`), entry point `mini-claude`
- `src/mini_claude/__init__.py`
- `src/mini_claude/client.py` — NVIDIA/OpenAI-compatible client, key validation
- `src/mini_claude/tools.py` — tool registry + JSON schemas
- `src/mini_claude/turn.py` — core model ↔ tool loop
- `src/mini_claude/repl.py` — interactive chat + `/model`
- `src/mini_claude/cli.py` — argparse: `-p`, `--model`
- `DESIGN.md` — this file
- `tests/unit/*.py` — unit tests
