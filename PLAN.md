# Plan: mini-claude — a small coding agent (mini Claude Code)

Goal: a Python coding agent with a core loop — send task to model, run requested
tools, send results back, repeat until the model stops asking. Model replies are
printed exactly as they came back.

## Conventions (Claude Code-style)
- Default mode: interactive chat REPL.
- Headless mode: `-p "task"` runs one task and exits.
- API key: `NVIDIA_API_KEY` from environment only. Never printed, never saved in
  the project, no `.env` handling.
- Model: `--model <id>` on the command line; `/model <id>` inside chat. Default: `nvidia/nemotron-3.5-lightning-30b-a3b` (Nemotron 3.5 Lightning, NVIDIA's agentic-task model; free tier).
- Ctrl-C: aborts the current turn, not the program (returns to REPL; headless
  exits cleanly with a message).
- NVIDIA API is OpenAI-compatible: base URL
  `https://integrate.api.nvidia.com/v1`.

## Repo layout (new git repo at /mnt/storage/projects/magitech/mini-claude)
- `pyproject.toml` — project metadata + deps (`openai` client; pytest/mypy/ruff
  as dev deps). uv-managed; lockfile committed.
- `src/mini_claude/__init__.py`
- `src/mini_claude/client.py` — NVIDIA/OpenAI-compatible client wrapper; key
  validation; clear error messages for missing key / bad model / network errors.
- `src/mini_claude/turn.py` — core turn loop (model call -> tool exec -> repeat).
- `src/mini_claude/tools.py` — tool registry: read_file, write_file,
  list_directory, grep_files, run_command.
- `src/mini_claude/repl.py` — interactive chat with `/model` command.
- `src/mini_claude/cli.py` — argparse: `-p`/`--prompt`, `--model`.
- `DESIGN.md` — how to run + every decision (kept up to date).
- `tests/unit/*.py` — flat test files, no `__init__.py`, AsyncMock seams.

## Tests to run
1. Headless: `uv run mini-claude -p "say hi in three words"` (needs user's key;
   mocked version in unit tests).
2. No key: unset `NVIDIA_API_KEY` → clear message, exit non-zero, no crash.
3. Bad model: `--model nope/nope` → clear API error message, no crash.

## Standards
- Follow shared uv / ruff skills; line length 88; strict mypy on `src/`;
- `uv run pytest --cov-fail-under=100` where achievable.

Unresolved questions: none.
