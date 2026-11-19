"""Replace exact text in a file you have already read. Replaces the first
occurrence of old_string with new_string.
"""

from pathlib import Path

from anima import Context, Service


class EditFileService(Service):
    """Replace exact text in a file you have already read.

    Replaces the first occurrence of old_string with new_string.

    Args:
        path: Path of a previously read file to edit.
        old_string: Exact text to replace.
        new_string: Text to replace old_string with.

    Returns:
        A confirmation message.
    """

    def __init__(self, ctx: Context):
        super().__init__(ctx, "edit_file")

    def __call__(
        self,
        *,
        path: str,
        old_string: str,
        new_string: str,
        read_files: set[str] | None = None,
    ) -> str:
        if read_files is not None and path not in read_files:
            return (
                f"Refused: '{path}' has not been read yet. "
                f"Call read_file on '{path}' first, then retry edit_file."
            )
        target = Path(path)
        text = target.read_text(encoding="utf-8")
        if old_string not in text:
            return (
                f"Error: old_string not found in {path}. "
                f"Call read_file on {path} to see the exact text (including "
                f"whitespace and indentation), then call edit_file again with "
                f"an exact old_string."
            )
        target.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
        return f"Replaced the first occurrence of old_string in {path}."
