"""Run a shell command on the host, optionally inside a Docker sandbox.

By default the command runs directly on the host (unsandboxed). This is the
same model most coding agents use: the user is present, sees every command,
and can abort any turn with Ctrl-C.

Set ``MAGECODE_SANDBOX=1`` or pass ``--sandbox`` to execute inside a throwaway
Docker container with --network none, --read-only root FS, dropped
capabilities, and resource limits.

Security note: unsandboxed commands run with the same privileges as the user,
including access to environment variables such as NVIDIA_API_KEY. Use the
sandbox mode if you run untrusted model-generated commands.
"""

from __future__ import annotations

import os
import shlex
import subprocess

from magecode.tools.registry import tool

_SANDBOX_ENV = "MAGECODE_SANDBOX"


def _decode_text(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def _use_sandbox() -> bool:
    return os.environ.get(_SANDBOX_ENV, "").lower() in ("1", "true", "yes", "on")


def _run_host(command: str, timeout: int) -> str:
    """Run *command* directly on the host and return a result string."""
    try:
        completed = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        return (
            f"Error: command not found: {error.filename}. Check the command and retry."
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


def _run_sandboxed(command: str, timeout: int) -> str:
    """Run *command* inside a Docker sandbox and return a result string."""
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


@tool
def run_command(*, command: str, timeout: float | int = 30) -> str:
    """Run a shell command on the host (default) or in a Docker sandbox.

    Default mode runs the command directly on the host with a timeout. The
    user is present, sees every command, and can abort any turn with Ctrl-C.

    Set MAGECODE_SANDBOX=1 in the environment to run inside a throwaway
    Docker container with --network none, --read-only root filesystem,
    dropped capabilities, and resource limits instead.

    Security note: unsandboxed commands run with the user's privileges,
    including access to environment variables such as NVIDIA_API_KEY. Use
    sandbox mode for untrusted model-generated commands.

    Args:
        command: Command line to run.
        timeout: Timeout in seconds (default 30).

    Returns:
        stdout, stderr, and exit code. Output is capped by the sandbox (8 KB
        per stream) when sandbox mode is enabled; host mode returns full
        output.
    """
    timeout = int(timeout)
    if _use_sandbox():
        return _run_sandboxed(command, timeout)
    return _run_host(command, timeout)
