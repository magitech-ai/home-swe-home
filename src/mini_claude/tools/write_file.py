"""Create or overwrite a file with the given text. After writing, the path
is marked readable so it can be edited with edit_file.
"""

from mini_claude.tools import tool


@tool
def write_file(*, path: str, content: str) -> str:
    """Create or overwrite a file with the given text.

    After writing, the path is marked readable so it can be edited with
    edit_file.

    Args:
        path: Path of the file to write.
        content: Text to write into the file.

    Returns:
        A confirmation message with the number of characters written.
    """
    from pathlib import Path

    Path(path).write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}."
