"""Run a shell command in a Docker sandbox."""

from magecode import sandbox
from magecode.tools.registry import tool


@tool
def run_command(*, command: str, timeout: float | int = 30) -> str:
    """Run a shell command in a Docker sandbox.

    The command executes inside a throwaway container with no network,
    a read-only root filesystem, dropped capabilities, and resource limits.
    The current directory is mounted as /workspace so the command can
    operate on project files.

    Args:
        command: Command line to run.
        timeout: Timeout in seconds (default 30).

    Returns:
        stdout, stderr, and exit code. Output is capped to avoid flooding
        the context window. If Docker is unavailable, returns an error.
    """
    result = sandbox.run_in_sandbox(command, timeout=int(timeout))
    parts: list[str] = []
    if result.stdout:
        parts.append(f"stdout:\n{result.stdout}")
    if result.stderr:
        parts.append(f"stderr:\n{result.stderr}")
    parts.append(f"exit code: {result.exit_code}")
    if result.timed_out:
        parts.append("timed out")
    return "\n".join(parts)
