"""Shared pytest fixtures: keep tests hermetic (no .env leakage)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_dotenv():
    """Never load the real .env during tests — it would mutate os.environ."""
    with patch("magecode.cli.load_dotenv"):
        yield
