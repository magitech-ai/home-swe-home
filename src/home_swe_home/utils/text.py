"""Small text helpers shared by home-swe-home's tool and sandbox Services."""

from __future__ import annotations


def decode_text(data: bytes | str | None) -> str:
    """Coerce subprocess output to text; ``None`` becomes an empty string."""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data
