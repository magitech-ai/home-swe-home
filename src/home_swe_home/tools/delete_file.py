"""Delete a file. Only files that exist can be deleted."""

from pathlib import Path

from anima import Context, Service


class DeleteFileService(Service):
    """Delete a file.

    Only files that exist can be deleted.

    Args:
        path: Exact path of the file to delete.

    Returns:
        A confirmation message naming the deleted file.
    """

    def __init__(self, ctx: Context):
        super().__init__(ctx, "delete_file")

    def __call__(self, *, path: str, read_files: set[str] | None = None) -> str:
        target = Path(path)
        try:
            target.unlink()
        except FileNotFoundError:
            msg = f"Error: FileNotFoundError: No such file or directory: '{path}'"
            return msg
        return f"Deleted {path}."
