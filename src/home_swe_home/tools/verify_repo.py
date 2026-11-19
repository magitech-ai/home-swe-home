"""Run the affected repository's own checks before declaring work done."""

from __future__ import annotations

from pathlib import Path

from anima import Context, Service

from ..utils.verify import (
    default_runner,
    format_results,
    run_checks,
    verification_commands,
)


class VerifyRepoService(Service):
    """Mounted as ``ctx.verify_repo`` and exposed as a model tool."""

    def __init__(self, ctx: Context):
        super().__init__(ctx, "verify_repo")

    def __call__(self, *, path: str = ".") -> str:
        """Run this repository's declared checks and report pass/fail.

        Call this on every affected repository before reporting a multi-repo
        task as done.
        """
        root = Path(path).resolve()
        return format_results(
            run_checks(verification_commands(root), default_runner, cwd=root)
        )
