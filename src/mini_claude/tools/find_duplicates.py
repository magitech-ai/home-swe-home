"""Find duplicate code blocks across Python files."""

from pathlib import Path

from mini_claude.tools import tool


@tool
def find_duplicates(*, path: str = "", min_lines: int = 3) -> str:
    """Find duplicate code blocks across Python files.

    Uses simple line-based comparison to find near-identical code sequences.
    Returns file:line ranges that are duplicated.

    Args:
        path: Directory path (defaults to current directory).
        min_lines: Minimum number of consecutive lines to consider a
            duplicate (defaults to 3).

    Returns:
        Matching blocks with file paths and line numbers.
    """
    if not path:
        path = "."

    root = Path(path)
    py_files: list[Path] = list(root.rglob("*.py"))

    # Read all files, storing lines
    file_lines: dict[Path, list[str]] = {}
    for f in py_files:
        try:
            text = f.read_text(encoding="utf-8")
            file_lines[f] = text.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

    seen: dict[str, list[tuple[Path, int]]] = {}

    for f, lines in file_lines.items():
        # Generate contiguous blocks of exactly min_lines
        for start in range(len(lines) - min_lines + 1):
            block = "\n".join(lines[start : start + min_lines])
            seen.setdefault(block, []).append((f, start + 1))

    duplicates: list[str] = []
    for block, locations in seen.items():
        if len(locations) > 1:
            duplicates.append(
                f"Duplicate block ({min_lines} lines):\n"
                + "\n".join(f"  {loc[0].name}:{loc[1]}" for loc in locations[:5])
                + f"\n  {block[:100]}...\n"
            )

    if not duplicates:
        return "No duplicate code blocks found."

    return f"Found {len(duplicates)} duplicate code blocks:\n" + "\n".join(duplicates)
