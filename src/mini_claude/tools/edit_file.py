"""Replace exact text in a file you have already read. Replaces the first
occurrence of old_string with new_string.
"""

from mini_claude.tools import tool


@tool(
    name="edit_file",
    manual=(
        "Replace exact text in a file you have already read. "
        "Replaces the first occurrence of old_string with "
        "new_string.\n"
        "Manual:\n"
        "  - You must have called read_file on this path first;\n"
        "    otherwise this tool is refused.\n"
        "  - old_string must match the file text exactly (including\n"
        "    whitespace and indentation).\n"
        "  - Only the first occurrence is replaced.\n"
        "  - If old_string is not found, the error says so; re-read\n"
        "    the file to see the exact text, then retry.\n"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path of a previously read file to edit.",
            },
            "old_string": {
                "type": "string",
                "description": "Exact text to replace.",
            },
            "new_string": {
                "type": "string",
                "description": "Text to replace old_string with.",
            },
        },
        "required": ["path", "old_string", "new_string"],
        "additionalProperties": False,
    },
)
def edit_file(*, path: str, old_string: str, new_string: str) -> str:
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
