"""Hot-reload a Python module from disk, picking up on-disk changes."""

import importlib
import importlib.util
import os
from contextlib import suppress
from pathlib import Path

from anima import Context, Service

# (mtime, size) of the last reload per module. importlib's bytecode cache is
# keyed on (integer mtime seconds, size), so tracking both avoids treating a
# same-size edit within the same second as "no change", and deleting the cache
# below avoids executing the stale bytecode in that case.
_module_stats: dict[str, tuple[float, int]] = {}


class ReloadModuleService(Service):
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

    def __init__(self, ctx: Context):
        super().__init__(ctx, "reload_module")

    def __call__(
        self,
        *,
        module_name: str,
        file_path: str,
        read_files: set[str] | None = None,
    ) -> str:
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
        try:
            stat = os.stat(path)
        except OSError:
            return f"Error: could not stat {path}."
        current = (stat.st_mtime, stat.st_size)

        # Skip if unchanged since last reload (mtime AND size).
        cached = _module_stats.get(module_name)
        if cached is not None and cached == current:
            return (
                f"No changes detected for module '{module_name}' "
                f"since last reload (mtime={cached[0]:.1f})."
            )

        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return f"Error: could not create spec for {path}."
        # importlib reuses cached bytecode when (mtime seconds, size) match,
        # so two same-size edits in one second would silently run stale code.
        # Delete the cache before executing the module.
        with suppress(ValueError, OSError):
            Path(importlib.util.cache_from_source(path)).unlink(missing_ok=True)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _module_stats[module_name] = current
        return f"Reloaded module '{module_name}' from {path} (mtime={current[0]:.1f})."
