"""Run a shell command with a timeout and return its output. This runs
arbitrary programs in the current directory.
"""

import shlex
import subprocess

from mini_claude.tools import tool


@tool(
    name="run_command",
    manual=(
        "Run a shell command with a timeout and return its output. "
        "This runs arbitrary programs in the current directory.\n"
        "Manual:\n"
        "  - Provide the command line as a single string.\n"
        "  - Optionally provide a timeout in seconds (default 30).\n"
        "  - Returns stdout, stderr, and exit code.\n"
        "  - On timeout or failure the result starts with 'Error:'.\n"
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command line to run.",
            },
            "timeout": {
                "type": "number",
                "description": "Timeout in seconds (default 30).",
            },
        },
        "required": ["command"],
        "additionalProperties": False,
    },
)
def run_command(*, command: str, timeout: float | int = 30) -> str:
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
