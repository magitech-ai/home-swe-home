"""Run a shell command with a timeout and return its output. This runs
arbitrary programs in the current directory.
"""

import shlex
import subprocess

from magecode.tools import tool


@tool
def run_command(*, command: str, timeout: float | int = 30) -> str:
    """Run a shell command with a timeout.

    Runs arbitrary programs in the current directory.

    Args:
        command: Command line to run.
        timeout: Timeout in seconds (default 30).

    Returns:
        stdout, stderr, and exit code.
    """
    completed = subprocess.run(
        shlex.split(command),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    parts: list[str] = []
    if completed.stdout:
        parts.append(f"stdout:\n{completed.stdout}")
    if completed.stderr:
        parts.append(f"stderr:\n{completed.stderr}")
    parts.append(f"exit code: {completed.returncode}")
    return "\n".join(parts)
