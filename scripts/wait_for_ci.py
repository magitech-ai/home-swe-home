#!/usr/bin/env python3
"""Wait until the required CI checks for a PR are terminal and passing.

The only evidence used is GitHub's check rollup: each CI check's name and
`bucket` (`pass`, `fail` or `pending`) from `gh pr checks --json`. The review
check is excluded by name prefix so this cannot wait on itself. A timeout is
a safety bound, never evidence that the checks passed.

Usage:
    python3 scripts/wait_for_ci.py --repo OWNER/REPO --pr 123 \
        --prefix "Test & Lint" --timeout 900 --interval 15
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any


def classify(
    checks: list[dict[str, Any]], prefix: str
) -> tuple[str, list[dict[str, Any]]]:
    """Summarise the CI checks that match ``prefix``.

    A failure wins over pending; only an all-passing set is a pass. An empty
    set or an unrecognised bucket is pending, never a pass.
    """
    matching = [
        check for check in checks if str(check.get("name", "")).startswith(prefix)
    ]
    if not matching:
        return "pending", []
    buckets = {check.get("bucket") for check in matching}
    if "fail" in buckets:
        return "fail", matching
    if buckets == {"pass"}:
        return "pass", matching
    return "pending", matching


def fetch(repo: str, pr: int) -> list[dict[str, Any]]:
    """Read the check rollup from GitHub. Pending checks make gh exit non-zero,
    so the exit status is ignored; the JSON on stdout is the fact we use."""
    proc = subprocess.run(
        [
            "gh",
            "pr",
            "checks",
            str(pr),
            "--repo",
            repo,
            "--json",
            "name,state,bucket,link",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if not proc.stdout.strip():
        return []
    return json.loads(proc.stdout)


def format_detail(details: list[dict[str, Any]]) -> str:
    return ", ".join(
        f"{check.get('name')}={check.get('bucket')} ({check.get('link', '')})"
        for check in details
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="OWNER/REPO")
    parser.add_argument("--pr", required=True, type=int, help="pull request number")
    parser.add_argument("--prefix", default="Test & Lint", help="CI check name prefix")
    parser.add_argument(
        "--timeout", type=int, default=900, help="safety bound in seconds"
    )
    parser.add_argument(
        "--interval", type=int, default=15, help="poll interval in seconds"
    )
    args = parser.parse_args(argv)

    deadline = time.monotonic() + args.timeout
    while True:
        state, details = classify(fetch(args.repo, args.pr), args.prefix)
        print(f"CI checks: {state}: {format_detail(details)}", flush=True)
        if state == "pass":
            return 0
        if state == "fail":
            return 1
        if time.monotonic() >= deadline:
            print(
                f"error: CI checks did not pass within {args.timeout}s",
                file=sys.stderr,
            )
            return 2
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
