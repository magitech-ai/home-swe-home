"""Replace exact text in a file you have already read. Replaces the first
occurrence of old_string with new_string.
"""

from mini_claude.tools import tool


@tool
def edit_file(*, path: str, old_string: str, new_string: str) -> str:
    """Replace exact text in a file you have already read.

    Replaces the first occurrence of old_string with new_string.

    Args:
        path: Path of a previously read file to edit.
        old_string: Exact text to replace.
        new_string: Text to replace old_string with.

    Returns:
        A confirmation message.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If old_string is not found in the file.
    """
    from pathlib import Path

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
