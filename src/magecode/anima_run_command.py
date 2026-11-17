"""Anima component: run_command shell tool.

A thin Service wrapper around magecode's sandboxed command execution.
Mount it on an anima Context with ``ctx.use(RunCommandService)``, then
access it as ``ctx.run_command`` or inject it into other components via
``inject = ["run_command"]``.
"""

from __future__ import annotations

import os
import shlex
import subprocess

from anima import Context, Service

_SANDBOX_ENV = "MAGECODE_SANDBOX"


def _use_sandbox() -> bool:
    return os.environ.get(_SANDBOX_ENV, "").lower() in ("1", "true", "yes", "on")


class RunCommandService(Service):
    """Run shell commands on the host (default) or in a Docker sandbox.

    Default mode runs the command directly on the host with a timeout.
    Set ``MAGECODE_SANDBOX=1`` to execute inside a throwaway Docker
    container with --network none, --read-only root FS, dropped
    capabilities, and resource limits.
    """

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "run_command")

    def __call__(self, command: str, timeout: float | int = 30) -> str:
        """Run *command* and return stdout, stderr, and exit code."""
        if _use_sandbox():
            return self._run_sandboxed(command, int(timeout))
        return self._run_host(command, int(timeout))

    def _run_host(self, command: str, timeout: int) -> str:
        try:
            completed = subprocess.run(
                shlex.split(command),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as error:
            return (
                f"Error: command not found: {error.filename}. "
                "Check the command and retry."
            )
        except subprocess.TimeoutExpired as error:
            stdout = _decode_text(getattr(error, "stdout", None))
            stderr = _decode_text(getattr(error, "stderr", None))
            timeout_parts: list[str] = []
            if stdout:
                timeout_parts.append(f"stdout:\n{stdout}")
            if stderr:
                timeout_parts.append(f"stderr:\n{stderr}")
            timeout_parts.append("exit code: 124")
            timeout_parts.append("timed out")
            return "\n".join(timeout_parts)
        parts: list[str] = []
        if completed.stdout:
            parts.append(f"stdout:\n{completed.stdout}")
        if completed.stderr:
            parts.append(f"stderr:\n{completed.stderr}")
        parts.append(f"exit code: {completed.returncode}")
        return "\n".join(parts)

    def _run_sandboxed(self, command: str, timeout: int) -> str:
        from magecode import sandbox

        result = sandbox.run_in_sandbox(command, timeout=timeout)
        parts: list[str] = []
        if result.stdout:
            parts.append(f"stdout:\n{result.stdout}")
        if result.stderr:
            parts.append(f"stderr:\n{result.stderr}")
        parts.append(f"exit code: {result.exit_code}")
        if result.timed_out:
            parts.append("timed out")
        return "\n".join(parts)


def _decode_text(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def mount_run_command(ctx: Context) -> None:
    """Mount the run_command service onto an anima Context."""
    ctx.use(RunCommandService)
