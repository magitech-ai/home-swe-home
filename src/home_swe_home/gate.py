"""Fail-closed gate controls for the factory.

The kill switch exists so a single action can stop automated review from
gating merges. When it is off, the review check fails closed — nothing merges
until a human deliberately re-enables it. No model call is made.
"""

from __future__ import annotations

import os
import sys

KILL_SWITCH_ENV = "HOME_SWE_HOME_REVIEW_ENABLED"
ENABLED_VALUE = "true"


def check_review_enabled(value: str | None) -> None:
    """Raise unless the review gate is explicitly enabled."""
    if value != ENABLED_VALUE:
        raise RuntimeError(
            "Agent review is disabled by kill switch "
            f"({KILL_SWITCH_ENV} != {ENABLED_VALUE!r}); failing closed. "
            "Set the repository variable AGENT_REVIEW_ENABLED to 'true' to "
            "re-enable."
        )


def main(argv: list[str] | None = None) -> int:
    try:
        check_review_enabled(os.environ.get(KILL_SWITCH_ENV))
    except RuntimeError as error:
        print(f"hsh-gate: {error}", file=sys.stderr)
        return 2
    print("hsh-gate: review enabled")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
