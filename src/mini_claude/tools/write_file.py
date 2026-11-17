"""Create or overwrite a file with the given text. After writing, the path
is marked readable so it can be edited with edit_file.
"""

from mini_claude.tools import tool


@tool(
    name="write_file",
    manual=(
        "Create or overwrite a file with the given text. "
        "After writing, the path is marked readable so it can be "
        "edited with edit_file.\n"
        "Manual:\n"
        "  - Provide the exact path and the full text content.\n"
        "  - This overwrites any existing file at that path.\n"
        "  - On error the result starts with 'Error:'; check the path\n"
        "    and directory permissions, then call write_file again.\n"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path of the file to write.",
            },
            "content": {
                "type": "string",
                "description": "Text to write into the file.",
            },
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
)
def write_file(*, path: str, content: str) -> str:
    from pathlib import Path

    Path(path).write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}."
