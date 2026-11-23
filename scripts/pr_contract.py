#!/usr/bin/env python3
"""Machine-check the PR contract before the paid reviewer runs.

Only facts GitHub can supply are checked: the trigger issue exists and is open,
and when the issue names paths, at least one of them is in the PR's diff.
Whether the diff actually resolves the issue is the reviewer's judgement and
is deliberately not duplicated here. Auto-revert PRs have no trigger issue and
are skipped.

    python3 scripts/pr_contract.py \
        --repo OWNER/REPO --issue 140 \
        --pr-body-file pr-body.txt --changed-files-file changed-files.txt
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# A path token must contain a slash or a source/config extension, and must not
# contain whitespace. Without the whitespace rule, a CI check name such as
# "Test & Lint / ci" in an issue body becomes a false scope finding.
_PATH_TOKEN = re.compile(r"`([^`\n]+)`|([\w./\-]+\.(?:py|md|yml|yaml|toml|json|txt))")
_SLASH_TOKEN = re.compile(r"[\w.\-]+(?:/[\w.\-]+)+")


def parse_trigger_issue(pr_body: str) -> int | None:
    match = re.search(r"Trigger issue:\s*#?(\d+)", pr_body)
    return int(match.group(1)) if match else None


def _looks_like_path(token: str) -> bool:
    token = token.strip()
    if not token or any(char.isspace() for char in token):
        return False
    return "/" in token or bool(re.search(r"\.\w+$", token))


def named_paths(issue_body: str) -> set[str]:
    """Path-like tokens the issue names, normalized for prefix comparison."""
    found: set[str] = set()
    for backtick, extension in _PATH_TOKEN.findall(issue_body):
        token = backtick or extension
        if _looks_like_path(token):
            found.add(_normalise(token))
    for token in _SLASH_TOKEN.findall(issue_body):
        if _looks_like_path(token):
            found.add(_normalise(token))
    return found


def _normalise(token: str) -> str:
    return token.strip().removeprefix("./").rstrip(".,;:)`")


def check(
    *,
    pr_body: str,
    issue_state: str,
    issue_body: str,
    changed_files: list[str],
    expected_issue: int | None = None,
) -> list[str]:
    """Return zero or more contract violations. No prose judgement is made."""
    problems: list[str] = []
    issue = parse_trigger_issue(pr_body)
    if issue is None:
        problems.append("PR body has no 'Trigger issue: #N' line")
    elif expected_issue is not None and issue != expected_issue:
        problems.append(
            f"PR body names trigger issue #{issue}, workflow resolved #{expected_issue}"
        )
    if issue_state.upper() != "OPEN":
        problems.append(f"trigger issue state is {issue_state!r}, expected OPEN")
    if not issue_body.strip():
        problems.append("trigger issue has no body")
    changed = {_normalise(path) for path in changed_files}
    paths = named_paths(issue_body)
    if paths and not any(
        path in file or file.endswith(path) for path in paths for file in changed
    ):
        preview = ", ".join(sorted(paths)[:4])
        problems.append(
            f"issue names {len(paths)} path(s) but none are in the diff: {preview}"
        )
    return problems


def fetch_issue(repo: str, issue: int) -> tuple[str, str]:
    proc = subprocess.run(
        ["gh", "issue", "view", str(issue), "--repo", repo, "--json", "state,body"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"cannot read issue #{issue}: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    return str(data.get("state", "")), str(data.get("body", ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="OWNER/REPO")
    parser.add_argument("--issue", required=True, type=int, help="trigger issue number")
    parser.add_argument("--pr-body-file", required=True, type=Path)
    parser.add_argument("--changed-files-file", required=True, type=Path)
    args = parser.parse_args(argv)

    pr_body = args.pr_body_file.read_text(encoding="utf-8")
    changed_files = [
        line.strip()
        for line in args.changed_files_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    try:
        state, issue_body = fetch_issue(args.repo, args.issue)
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    problems = check(
        pr_body=pr_body,
        issue_state=state,
        issue_body=issue_body,
        changed_files=changed_files,
        expected_issue=args.issue,
    )
    if problems:
        print("PR contract failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(f"PR contract OK (trigger issue #{args.issue} is {state})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
