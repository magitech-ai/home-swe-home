"""home-swe-home's tool definitions for magitech-harness.

All tools are defined in ``definitions.py`` as mth ``ToolDefinition`` dicts
and registered on ``ctx.tools`` via ``register_tools(ctx)``.
"""

from .definitions import ALL_TOOLS, register_tools

__all__ = ["ALL_TOOLS", "register_tools"]