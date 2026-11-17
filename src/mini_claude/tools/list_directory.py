"""List the entries of a directory. Use this to verify what files exist after
writing or deleting.
"""

from mini_claude.tools import tool


@tool
def list_directory(*, path: str = ".") -> str:
    """List the entries of a directory.

    Args:
        path: Directory path (defaults to the current directory).

    Returns:
        One entry per line; directories end with '/'.
    """
    from pathlib import Path

    entries = sorted(Path(path).iterdir())
    lines: list[str] = []
    for entry in entries:
        lines.append(f"{entry.name}/" if entry.is_dir() else entry.name)
    return "\n".join(lines) if lines else "(empty)"
