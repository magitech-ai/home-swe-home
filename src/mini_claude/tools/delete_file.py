"""Delete a file. Only files that exist can be deleted."""

from mini_claude.tools import tool


@tool(
    name="delete_file",
    manual=(
        "Delete a file. Only files that exist can be deleted.\n"
        "Manual:\n"
        "  - Provide the exact path of the file to delete.\n"
        "  - Returns confirmation naming the deleted file.\n"
        "  - On error the result starts with 'Error:'; check the path\n"
        "    and try again.\n"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Exact path of the file to delete.",
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)
def delete_file(*, path: str) -> str:
    from pathlib import Path

    target = Path(path)
    target.unlink()
    return f"Deleted {path}."
