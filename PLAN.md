# Plan: add file tools + web search with manuals and strict rules

Goal: give mini-claude hands — read, write, edit, delete files; run commands;
search the project; search the web. Every tool has a manual (schema
description) the model reads, strict input rules, and errors that say what to
try next. Edits replace exact text only in files the model has read. Every tool
call returns an answer, even on failure.

## New / changed tools (schemas in tools.py)
- read_file — returns contents; marks path as read (required before edit)
- write_file — create/overwrite; also marks path writable/editable
- edit_file (NEW) — exact old_string→new_string replace; only in read files
- delete_file (NEW) — remove a file; confirm what was deleted
- run_command (exists) — shell command with timeout
- grep_files (exists) — regex search across files
- web_search (NEW) — DuckDuckGo HTML endpoint, no API key

## Rules enforced by code
- edit_file refuses unless the path was read via read_file (tracked per turn)
- old_string must match exactly; otherwise error says what to try next
- Every tool failure returns text (never crashes); error includes next step
- Tool results go back to the model as `tool` messages; turn repeats

## Design doc updates
- Add every tool's manual (schema description) + strict input rules
- Document read-before-edit constraint and web search choice

## Live tests (user runs with their key)
1. "create a script that prints hi, run it, and tell me the output"
   → write hi.py, run python hi.py, report "hi"
2. "replace a line that isn't in the script"
   → error: old_string not found; try read_file + exact text
3. "delete the file and check that it deleted the one file and nothing else"
   → delete_file hi.py, then list_directory to confirm only hi.py is gone

Unresolved questions: none.
