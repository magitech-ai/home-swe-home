"""Delete a file. Only files that exist can be deleted."""

from magecode.tools.registry import tool


@tool
def delete_file(*, path: str) -> str:
    """Delete a file.

    Only files that exist can be deleted.

    Args:
        path: Exact path of the file to delete.

    Returns:
        A confirmation message naming the deleted file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    from pathlib import Path

    target = Path(path)
    target.unlink()
    return f"Deleted {path}."
