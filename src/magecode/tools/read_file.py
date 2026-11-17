"""Read a file's text contents. Marks the path as readable (required before
calling edit_file on that path).
"""

from pathlib import Path

from magecode.tools.registry import tool


@tool
def read_file(*, path: str, read_files: set[str] | None = None) -> str:
    """Read a file and return its text contents.

    Reading a file marks it as readable, which is required before calling
    edit_file on that path.

    Args:
        path: Exact path of the file to read.

    Returns:
        The full file text (large files may be truncated).

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    result = Path(path).read_text(encoding="utf-8")
    if read_files is not None:
        read_files.add(path)
    return result
