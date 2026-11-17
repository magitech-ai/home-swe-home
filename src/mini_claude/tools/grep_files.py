"""Search files for a regex pattern. Returns matching lines with
file:line:content, capped at 50 matches.
"""

import re
from pathlib import Path

from mini_claude.tools import tool


@tool
def grep_files(*, pattern: str, path: str = ".") -> str:
    """Search files for a regex pattern.

    Returns matching lines with file:line:content, capped at 50 matches.

    Args:
        pattern: Regular expression to search for.
        path: Directory to search (defaults to '.').

    Returns:
        Matching lines, or 'No matches.' if nothing is found.
    """
    regex = re.compile(pattern)
    root = Path(path)
    matches: list[str] = []

    # If path is a file, search just that file; otherwise rglob the directory
    if root.is_file():
        files_to_search = [root]
    else:
        files_to_search = root.rglob("*")

    for file in files_to_search:
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
