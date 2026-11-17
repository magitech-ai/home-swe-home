"""Hot-reload a Python module from disk, picking up on-disk changes."""

import importlib
import importlib.util
import os

from magecode.tools.executor import _module_mtimes
from magecode.tools.registry import tool


@tool
def reload_module(
    *,
    module_name: str,
    file_path: str,
    read_files: set[str] | None = None,
) -> str:
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
    if read_files is None:
        return "Refused: reload_module requires a read_files tracker."
    if file_path not in read_files:
        return (
            f"Refused: '{file_path}' has not been read yet. "
            f"Call read_file on '{file_path}' first, then retry reload_module."
        )
    path = os.path.abspath(file_path)
    if not path.endswith(".py"):
        path = path + ".py"
    # Optional optimisation: skip if mtime hasn't changed since last reload.
    cached = _module_mtimes.get(module_name)
    if cached is not None:
        try:
            current_mtime = os.path.getmtime(path)
        except OSError:
            current_mtime = None
        if current_mtime is not None and current_mtime == cached:
            return (
                f"No changes detected for module '{module_name}' "
                f"since last reload (mtime={cached:.1f})."
            )
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return f"Error: could not create spec for {path}."
    _module_mtimes.pop(module_name, None)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _module_mtimes[module_name] = os.path.getmtime(path)
    return (
        f"Reloaded module '{module_name}' from {path} "
        f"(mtime={_module_mtimes[module_name]:.1f})."
    )
