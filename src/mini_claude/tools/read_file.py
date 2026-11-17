"""Read a file's text contents. Marking a path as readable is required before
calling edit_file on that path.
"""

from mini_claude.tools import tool


@tool(
    name="read_file",
    manual=(
        "Read a file and return its text contents. "
        "Reading a file marks it as readable, which is required "
        "before calling edit_file on that path.\n"
        "Manual:\n"
        "  - Provide the exact path of the file to read.\n"
        "  - Returns the full file text (large files may be truncated).\n"
        "  - After a successful read, the path is marked readable.\n"
        "  - On error the result starts with 'Error:'; fix the path or\n"
        "    permissions and call read_file again.\n"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Exact path of the file to read.",
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)
def read_file(*, path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8")
