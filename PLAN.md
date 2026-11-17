# Plan: session instructions + token counting + /context

Goal: The model sees a system message (instructions) on every call, written once
per session. It includes short rules, a system line (OS, folder, date, model),
and the project's AGENTS.md if present. The system message is never rewritten;
new information is appended at the end so the prompt cache stays valid.

## Changes
- `src/magecode/instructions.py` (NEW): build_system_instructions() — rules,
  system line, AGENTS.md content; count_tokens() using tiktoken
- `src/magecode/cli.py`: prepend system message to headless messages
- `src/magecode/repl.py`: prepend system message to chat messages;
  `/context` command prints context window + token counts
- `src/magecode/turn.py`: print token count before each model call
- `pyproject.toml`: add tiktoken dependency
- `DESIGN.md`: document instructions + /context rule

## Tests
- Unit: build_system_instructions includes rules/system line/AGENTS.md
- Unit: count_tokens returns positive int
- Unit: system message is first and immutable in messages list
- Live: AGENTS.md with "Always answer in French" → hello in French
- Live: delete AGENTS.md, new session → hello in English

Unresolved questions: none.
