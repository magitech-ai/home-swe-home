"""Read a file's text contents. Marking a path as readable is required before
calling edit_file on that path.
"""

from magecode.tools import tool


@tool
def read_file(*, path: str) -> str:
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
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8")
