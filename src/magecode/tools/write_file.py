"""Create or overwrite a file with the given text. After writing, the path
is marked readable so it can be edited with edit_file.
"""

from pathlib import Path

from magecode.tools.registry import tool


@tool
def write_file(*, path: str, content: str, read_files: set[str] | None = None) -> str:
    """Create or overwrite a file with the given text.

    After writing, the path is marked readable so it can be edited with
    edit_file.

    Args:
        path: Path of the file to write.
        content: Text to write into the file.

    Returns:
        A confirmation message with the number of characters written.
    """
    Path(path).write_text(content, encoding="utf-8")
    if read_files is not None:
        read_files.add(path)
    return f"Wrote {len(content)} characters to {path}."
