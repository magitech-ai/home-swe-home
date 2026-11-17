"""Anima component: greeter that depends on run_command.

Demonstrates the "everything is a component" pattern: this service
declares ``inject = ["run_command"]`` so the anima context injects the
run_command service dependency automatically.
"""

from __future__ import annotations

from anima import Context, Service

from magecode.anima_run_command import RunCommandService


class GreeterService(Service):
    """Greets by running 'whoami' via the injected run_command service."""

    inject = ["run_command"]

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "greeter")

    def greet(self) -> str:
        """Run whoami through the injected run_command service and return a greeting."""
        result = self.ctx.run_command("whoami", timeout=5)
        # Output format: "stdout:\n<name>\n\nexit code: 0"
        lines = result.strip().splitlines()
        username = "unknown"
        for line in lines:
            if line and not line.startswith(("stdout:", "exit code:")):
                username = line.strip()
                break
        return f"Hello, {username}! I am greeter, running on anima."


def mount_greeter(ctx: Context) -> None:
    """Mount the greeter service (and its run_command dependency) onto a Context."""
    ctx.use(RunCommandService)
    ctx.use(GreeterService)
