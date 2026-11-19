"""List the entries of a directory."""

from pathlib import Path

from anima import Context, Service


class ListDirectoryService(Service):
    """List the entries of a directory.

    Args:
        path: Directory path (defaults to the current directory).

    Returns:
        One entry per line; directories end with '/'.
    """

    def __init__(self, ctx: Context):
        super().__init__(ctx, "list_directory")

    def __call__(
        self,
        *,
        path: str = ".",
        read_files: set[str] | None = None,
    ) -> str:
        entries = sorted(Path(path).iterdir())
        lines: list[str] = []
        for entry in entries:
            lines.append(f"{entry.name}/" if entry.is_dir() else entry.name)
        return "\n".join(lines) if lines else "(empty)"
