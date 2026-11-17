"""Hot-reload a Python module from disk, picking up on-disk changes."""

import importlib
import importlib.util
import os

from magecode.tools import tool


@tool
def reload_module(*, module_name: str, file_path: str) -> str:
    """Hot-reload a Python module from disk.

    Picks up any changes made since the last import. The module file must be
    a valid .py file importable by importlib.

    Args:
        module_name: Name to assign to the re-loaded module (must be a valid
            Python identifier).
        file_path: Absolute or relative path to the .py file containing the
            module source.

    Returns:
        A short status message summarising the reload.
    """
    path = os.path.abspath(file_path)
    if not path.endswith(".py"):
        path = path + ".py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return f"Error: could not create spec for {path}."
    # Reset any prior mtime tracking so we always re-load.
    from magecode.tools import _module_mtimes

    _module_mtimes.pop(module_name, None)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _module_mtimes[module_name] = os.path.getmtime(path)

    return (
        f"Reloaded module '{module_name}' from {path} "
        f"(mtime={_module_mtimes[module_name]:.1f})."
    )
