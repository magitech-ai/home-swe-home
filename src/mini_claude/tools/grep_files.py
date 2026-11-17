"""Search files for a regex pattern. Returns matching lines with
file:line:content, capped at 50 matches.
"""

import re
from pathlib import Path

from mini_claude.tools import tool


@tool(
    name="grep_files",
    manual=(
        "Search files for a regex pattern. Returns matching lines "
        "with file:line:content, capped at 50 matches.\n"
        "Manual:\n"
        "  - Provide a regular expression pattern.\n"
        "  - Optionally provide a directory to search (defaults to '.').\n"
        "  - Binary and unreadable files are skipped.\n"
        "  - Returns 'No matches.' if nothing is found.\n"
        "  - On error the result starts with 'Error:'; check the path\n"
        "    and try again.\n"
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression to search for.",
            },
            "path": {
                "type": "string",
                "description": "Directory to search (defaults to '.').",
            },
        },
        "required": ["pattern"],
        "additionalProperties": False,
    },
)
def grep_files(*, pattern: str, path: str = ".") -> str:
    regex = re.compile(pattern)
    root = Path(path)
    matches: list[str] = []
    for file in root.rglob("*"):
        if not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # skip binaries and unreadable files
        for line_number, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{file}:{line_number}: {line}")
                if len(matches) >= 50:
                    break
        if len(matches) >= 50:
            break
    return "\n".join(matches) if matches else "No matches."
