"""Hot-reload a Python module from disk, picking up on-disk changes."""

import importlib
import importlib.util
import os

from mini_claude.tools import tool


@tool(
    name="reload_module",
    manual=(
        "Hot-reload a Python module from disk, picking up any changes "
        "made since the last import.  The module file must be a valid "
        ".py file importable by importlib.  If the file's mtime has\n"
        "not changed since the last reload, the function reports that "
        "no reload was performed.\n\n"
        "Usage:\n"
        "  1. `read_file` the module you want to modify.\n"
        "  2. Edit it with `edit_file`.\n"
        "  3. Call `reload_module` with the same module name and the\n"
        "     file path.  The module's top-level namespace will be "
        "re-executed from disk.\n\n"
        "Note: only the module's own namespace is refreshed; other "
        "parts of the harness that import from it will keep references\n"
        "to the old objects unless they re-import.\n"
        "On error: check the module name and file path, retry.\n"
    ),
    parameters={
        "type": "object",
        "properties": {
            "module_name": {
                "type": "string",
                "description": (
                    "Name to assign to the re-loaded module "
                    "(must be a valid Python identifier)."
                ),
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Absolute or relative path to the .py file "
                    "containing the module source."
                ),
            },
        },
        "required": ["module_name", "file_path"],
        "additionalProperties": False,
    },
)
def reload_module(*, module_name: str, file_path: str) -> str:
    from mini_claude.tools import _module_mtimes

    path = os.path.abspath(file_path)
    if not path.endswith(".py"):
        path = path + ".py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return f"Error: could not create spec for {path}."
    # Reset any prior mtime tracking so we always re-load.
    _module_mtimes.pop(module_name, None)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _module_mtimes[module_name] = os.path.getmtime(path)

    return (
        f"Reloaded module '{module_name}' from {path} "
        f"(mtime={_module_mtimes[module_name]:.1f})."
    )
