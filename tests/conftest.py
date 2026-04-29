"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "extractors" / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURE_DIR
