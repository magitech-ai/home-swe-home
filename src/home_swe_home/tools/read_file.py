"""Read a file's text contents. Marking a path as readable is required before
calling edit_file on that path.
"""

from pathlib import Path

from anima import Context, Service


class ReadFileService(Service):
    """Read a file and return its text contents.

    Reading a file marks it as readable, which is required before calling
    edit_file on that path.

    Args:
        path: Exact path of the file to read.

    Returns:
        The full file text (large files may be truncated).
    """

    def __init__(self, ctx: Context):
        super().__init__(ctx, "read_file")

    def __call__(self, *, path: str, read_files: set[str] | None = None) -> str:
        result = Path(path).read_text(encoding="utf-8")
        if read_files is not None:
            read_files.add(path)
        return result
