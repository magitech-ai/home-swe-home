"""Search files for a regex pattern."""

import re
from pathlib import Path

from anima import Context, Service


class GrepFilesService(Service):
    """Search files for a regex pattern.

    Returns matching lines with file:line:content, capped at 50 matches.

    Args:
        pattern: Regular expression to search for.
        path: Directory to search (defaults to '.').

    Returns:
        Matching lines, or 'No matches.' if nothing is found.
    """

    def __init__(self, ctx: Context):
        super().__init__(ctx, "grep_files")

    def __call__(
        self,
        *,
        pattern: str,
        path: str = ".",
        read_files: set[str] | None = None,
    ) -> str:
        regex = re.compile(pattern)
        root = Path(path)
        matches: list[str] = []

        if root.is_file():
            files_to_search: list[Path] = [root]
        else:
            files_to_search = list(root.rglob("*"))

        for file in files_to_search:
            if not file.is_file():
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{file}:{line_number}: {line}")
                    if len(matches) >= 50:
                        break
            if len(matches) >= 50:
                break
        return "\n".join(matches) if matches else "No matches."
