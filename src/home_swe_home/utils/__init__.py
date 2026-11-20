"""Pure utility helpers for home-swe-home (not Services).

These are the documented exceptions to "everything is a component":
stateless helpers with no lifecycle. Service capabilities live in their own
Service classes; these support them.
"""

from __future__ import annotations

from .text import decode_text

__all__ = ["decode_text"]