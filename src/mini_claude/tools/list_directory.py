"""List the entries of a directory. Use this to verify what files exist after
writing or deleting.
"""

from mini_claude.tools import tool


@tool(
    name="list_directory",
    manual=(
        "List the entries of a directory. Use this to verify what "
        "files exist after writing or deleting.\n"
        "Manual:\n"
        "  - Provide a directory path (defaults to '.').\n"
        "  - Returns one entry per line; directories end with '/'.\n"
        "  - On error the result starts with 'Error:'.\n"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory to list (defaults to '.').",
            }
        },
        "required": [],
        "additionalProperties": False,
    },
)
def list_directory(*, path: str = ".") -> str:
    from pathlib import Path

    entries = sorted(Path(path).iterdir())
    lines: list[str] = []
    for entry in entries:
        lines.append(f"{entry.name}/" if entry.is_dir() else entry.name)
    return "\n".join(lines) if lines else "(empty)"
